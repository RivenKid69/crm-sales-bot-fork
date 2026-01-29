
import sys
import os

# Add project root and src to path
root = os.getcwd()
sys.path.insert(0, root)
sys.path.insert(0, os.path.join(root, "src"))

from src.classifier.refinement_pipeline import RefinementLayerRegistry
from src.classifier.unified import UnifiedClassifier

print("--- Initial state ---")
registry = RefinementLayerRegistry.get_registry()
print(f"Registry ID: {id(registry)}")
print(f"Registered layers: {registry.get_all_names()}")

print("\n--- Initializing UnifiedClassifier ---")
unified = UnifiedClassifier()
# This should trigger registration
pipeline = unified.refinement_pipeline

print(f"\nRegistry ID after init: {id(registry)}")
print(f"Registered layers after init: {registry.get_all_names()}")

print("\n--- Pipeline layers ---")
print(f"Pipeline layers: {[l.name for l in pipeline._layers]}")
