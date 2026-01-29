import sys
import os

# Add src to sys.path like simulator DOES NOT do anymore, 
# but we do it here to FORCE a test of duplication.
src_path = os.path.abspath("src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

print(f"--- RUNNING VERIFICATION ---")
print(f"CWD: {os.getcwd()}")
print(f"sys.path[0]: {sys.path[0]}")

# 1. Import registry via 'src.' prefix
from src.classifier.refinement_pipeline import RefinementLayerRegistry as RegistrySrc
reg_src = RegistrySrc.get_registry()
print(f"Registry (src.): {id(reg_src)} [ID: {id(RegistrySrc)}]")

# 2. Import registry WITHOUT 'src.' prefix
# Even if we import without src., the internal imports in refinement_pipeline.py 
# are now absolute 'src.', so it SHOULD land in the same instance if the class itself is same.
# Wait, if RegistryNoSrc is a different class object, it will have its own _instance.
import classifier.refinement_pipeline as rp_no_src
RegistryNoSrc = rp_no_src.RefinementLayerRegistry
reg_no_src = RegistryNoSrc.get_registry()
print(f"Registry (no src.): {id(reg_no_src)} [ID: {id(RegistryNoSrc)}]")

# 3. Check if they are the same
if reg_src is reg_no_src:
    print("SUCCESS: Registries are the same instance.")
else:
    print("WARNING: Registries are DIFFERENT instances (expected if classes are different).")

# The real fix is that UnifiedClassifier now uses absolute imports!
# Let's check UnifiedClassifier
print("\n--- Checking UnifiedClassifier ---")
# Import as both src. and non-src.
import src.classifier.unified as uc_src
import classifier.unified as uc_no_src

uc1 = uc_src.UnifiedClassifier()
uc2 = uc_no_src.UnifiedClassifier()

print(f"UnifiedClassifier (src.) refinement_pipeline ID: {id(uc1.refinement_pipeline)}")
print(f"UnifiedClassifier (no src.) refinement_pipeline ID: {id(uc2.refinement_pipeline)}")

if id(uc1.refinement_pipeline) == id(uc2.refinement_pipeline):
    print("SUCCESS: UnifiedClassifier uses the SAME refinement pipeline instance in both cases!")
else:
    print("FAILURE: UnifiedClassifier uses DIFFERENT refinement pipeline instances!")

# Check layers
print("\n--- Checking Layer Registration ---")
from src.classifier import refinement_layers
print(f"Layers in Registry: {reg_src.get_all_names()}")
