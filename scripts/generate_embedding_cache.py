"""
Generate embedding cache (.npy files) using Qwen3-Embedding-4B directly via transformers.

Bypasses TEI — loads model on GPU and encodes all texts.
The resulting .npy files are identical to what TEI would produce.

Usage:
    python scripts/generate_embedding_cache.py

Generates 4 cache files in .cache/embeddings/:
  - kb_sections_<hash>.npy
  - intent_examples_<hash>.npy
  - tone_examples_<hash>.npy
  - industry_profiles_<hash>.npy
"""

import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, ".")

CACHE_DIR = Path(".cache/embeddings")
MODEL_ID = "Qwen/Qwen3-Embedding-4B"


def texts_hash(texts):
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def load_model():
    from transformers import AutoModel, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    # Force fp32 to match local_tei_server.py on CPU — avoids fp16↔fp32 embedding mismatch
    dt = torch.float32
    print(f"Loading {MODEL_ID} on {device} (dtype=fp32) ...")
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModel.from_pretrained(MODEL_ID, dtype=dt, trust_remote_code=True)
    model = model.to(device).eval()
    print(f"Model loaded in {time.time() - t0:.1f}s")
    return model, tokenizer


def encode_batch(model, tokenizer, texts, batch_size=32):
    """Encode texts with last-token pooling (Qwen3-Embedding style)."""
    all_embeddings = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        device = next(model.parameters()).device
        inputs = tokenizer(batch, padding=True, truncation=True, max_length=8192, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model(**inputs)
            # Last token pooling (standard for Qwen3-Embedding)
            last_hidden = outputs.last_hidden_state
            attention_mask = inputs["attention_mask"]
            # Find last non-padding token for each sequence
            seq_lengths = attention_mask.sum(dim=1) - 1
            batch_indices = torch.arange(last_hidden.size(0), device=last_hidden.device)
            embeddings = last_hidden[batch_indices, seq_lengths]
            # L2 normalize
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            all_embeddings.append(embeddings.cpu().float().numpy())

        done = min(start + batch_size, len(texts))
        print(f"  encoded {done}/{len(texts)}")

    return np.concatenate(all_embeddings, axis=0)


def save_cache(name, texts, embeddings):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    content_hash = texts_hash(texts)
    npy_path = CACHE_DIR / f"{name}_{content_hash}.npy"

    # Remove old cache files for this name
    for old in CACHE_DIR.glob(f"{name}_*.npy"):
        old.unlink()

    np.save(npy_path, embeddings)
    print(f"  Saved: {npy_path} (shape={embeddings.shape})")


def main():
    model, tokenizer = load_model()
    total_start = time.time()

    # 1. KB sections (enriched: [category/topic] keywords. facts)
    from src.knowledge import WIPON_KNOWLEDGE as kb
    from src.knowledge.base import section_embed_text
    kb_texts = [section_embed_text(s) for s in kb.sections]
    print(f"\n=== KB sections: {len(kb_texts)} ===")
    t0 = time.time()
    kb_emb = encode_batch(model, tokenizer, kb_texts)
    save_cache("kb_sections", kb_texts, kb_emb)
    print(f"  Time: {time.time() - t0:.1f}s")

    # 2. Intent examples
    from src.classifier.intents.examples import INTENT_EXAMPLES
    intent_texts = []
    for intent, examples in INTENT_EXAMPLES.items():
        intent_texts.extend(examples)
    print(f"\n=== Intent examples: {len(intent_texts)} ===")
    t0 = time.time()
    intent_emb = encode_batch(model, tokenizer, intent_texts)
    save_cache("intent_examples", intent_texts, intent_emb)
    print(f"  Time: {time.time() - t0:.1f}s")

    # 3. Tone examples
    from src.tone_analyzer.examples import TONE_EXAMPLES
    tone_texts = []
    for tone_str, examples in TONE_EXAMPLES.items():
        tone_texts.extend(examples)
    print(f"\n=== Tone examples: {len(tone_texts)} ===")
    t0 = time.time()
    tone_emb = encode_batch(model, tokenizer, tone_texts)
    save_cache("tone_examples", tone_texts, tone_emb)
    print(f"  Time: {time.time() - t0:.1f}s")

    # 4. Pain KB sections
    from src.knowledge.pain_loader import load_pain_knowledge_base
    pain_kb = load_pain_knowledge_base()
    pain_texts = [section_embed_text(s) for s in pain_kb.sections]
    print(f"\n=== Pain KB sections: {len(pain_texts)} ===")
    t0 = time.time()
    pain_emb = encode_batch(model, tokenizer, pain_texts)
    save_cache("pain_sections", pain_texts, pain_emb)
    print(f"  Time: {time.time() - t0:.1f}s")

    # 5. Industry profiles
    from src.personalization.industry_detector import IndustryDetectorV2
    industry_texts = [p["description"] for p in IndustryDetectorV2.INDUSTRY_PROFILES.values()]
    print(f"\n=== Industry profiles: {len(industry_texts)} ===")
    t0 = time.time()
    industry_emb = encode_batch(model, tokenizer, industry_texts)
    save_cache("industry_profiles", industry_texts, industry_emb)
    print(f"  Time: {time.time() - t0:.1f}s")

    print(f"\n{'='*50}")
    print(f"Total: {time.time() - total_start:.1f}s")
    print("All caches generated!")


if __name__ == "__main__":
    main()
