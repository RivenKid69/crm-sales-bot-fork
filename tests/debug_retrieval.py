"""Debug: check what retrieved_facts come back for price questions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaLLM
from src.bot import SalesBot

llm = OllamaLLM()
bot = SalesBot(llm, flow_name="autonomous", enable_tracing=True)

# First turn to get past greeting
bot.process("Привет")

# Now ask about pricing
result = bot.process("Сколько стоит ваша система?")

# Get the trace
trace = result.get("decision_trace", {})
gen_meta = bot.generator._last_generation_meta
print("=== GENERATOR META ===")
print(f"selected_template: {gen_meta.get('selected_template_key')}")
print(f"fact_keys: {gen_meta.get('fact_keys')}")
print()

# Check what retrieved_facts were used
# Directly call the retrieval
from src.knowledge.retriever import get_retriever
from src.knowledge.enhanced_retrieval import EnhancedRetrievalPipeline

kb = get_retriever().kb
pipeline = bot.generator._enhanced_pipeline

facts, urls, keys = pipeline.retrieve(
    user_message="Сколько стоит ваша система?",
    intent="price_question",
    state="autonomous_discovery",
    flow_config=bot.generator._flow,
    kb=kb,
    recently_used_keys=set(),
    history=[],
    secondary_intents=[],
)

print("=== RETRIEVED FACTS ===")
print(f"Length: {len(facts)}")
print(f"Fact keys: {keys}")
print()
print(facts[:3000] if facts else "(EMPTY)")
