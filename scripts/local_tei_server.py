"""
Local TEI-compatible server for Qwen3-Embedding-4B + Qwen3-Reranker-4B.

Serves the same HTTP API as TEI:
  - POST /embed  (embedding)
  - POST /rerank (reranking)
  - GET  /health

Usage:
    python scripts/local_tei_server.py [--port 8081] [--reranker-port 8082]
"""

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from transformers import AutoModel, AutoTokenizer, AutoModelForCausalLM

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

_EMBED_MODEL_ID = os.environ.get("TEI_EMBED_MODEL_ID", "Qwen/Qwen3-Embedding-4B")
_EMBED_REVISION = os.environ.get("TEI_EMBED_REVISION", "5cf2132abc99cad020ac570b19d031efec650f2b")
_RERANK_MODEL_ID = os.environ.get("TEI_RERANK_MODEL_ID", "Qwen/Qwen3-Reranker-4B")
_RERANK_REVISION = os.environ.get("TEI_RERANK_REVISION", "f16fc5d5d2b9b1d0db8280929242745d79794ef5")


# ---- Embedding model ----

_embed_model = None
_embed_tokenizer = None
_EMBED_MAX_LENGTH = 8192
_EMBED_CHUNK_SIZE = 8
_RERANK_MAX_LENGTH = 4096


def _model_inputs(inputs, model):
    if getattr(model, "hf_device_map", None):
        return inputs
    device = next(model.parameters()).device
    return inputs.to(device)


def _offload_kwargs(gpu_cap_gib: int):
    if not torch.cuda.is_available():
        return {}

    return {
        "device_map": "auto",
        "max_memory": {
            0: f"{gpu_cap_gib}GiB",
            "cpu": "128GiB",
        },
        "low_cpu_mem_usage": True,
    }


def load_embed_model():
    global _embed_model, _embed_tokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dt = torch.float16 if device == "cuda" else torch.float32
    print(f"[embed] Loading {_EMBED_MODEL_ID}@{_EMBED_REVISION} on {device} ...")
    t0 = time.time()
    _embed_tokenizer = AutoTokenizer.from_pretrained(
        _EMBED_MODEL_ID,
        revision=_EMBED_REVISION,
        trust_remote_code=True,
    )
    _embed_model = AutoModel.from_pretrained(
        _EMBED_MODEL_ID,
        torch_dtype=dt,
        revision=_EMBED_REVISION,
        trust_remote_code=True,
        **_offload_kwargs(gpu_cap_gib=8),
    ).eval()
    if not getattr(_embed_model, "hf_device_map", None):
        _embed_model = _embed_model.to(device)
    print(f"[embed] Loaded in {time.time() - t0:.1f}s")


def _embed_batch(texts, max_length=_EMBED_MAX_LENGTH):
    inputs = _embed_tokenizer(
        texts, padding=True, truncation=True, max_length=max_length, return_tensors="pt"
    )
    inputs = _model_inputs(inputs, _embed_model)
    with torch.no_grad():
        outputs = _embed_model(**inputs)
        last_hidden = outputs.last_hidden_state
        attention_mask = inputs["attention_mask"]
        seq_lengths = attention_mask.sum(dim=1) - 1
        batch_indices = torch.arange(last_hidden.size(0), device=last_hidden.device)
        embeddings = last_hidden[batch_indices, seq_lengths]
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
    return embeddings.cpu().float().tolist()


def embed_texts(texts):
    results = []
    for start in range(0, len(texts), _EMBED_CHUNK_SIZE):
        chunk = texts[start:start + _EMBED_CHUNK_SIZE]
        try:
            results.extend(_embed_batch(chunk))
        except torch.OutOfMemoryError:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if len(chunk) == 1:
                results.extend(_embed_batch(chunk, max_length=4096))
                continue

            mid = max(1, len(chunk) // 2)
            results.extend(embed_texts(chunk[:mid]))
            results.extend(embed_texts(chunk[mid:]))
    return results


# ---- Reranker model ----

_rerank_model = None
_rerank_tokenizer = None


def load_rerank_model():
    global _rerank_model, _rerank_tokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dt = torch.float16 if device == "cuda" else torch.float32
    print(f"[rerank] Loading {_RERANK_MODEL_ID}@{_RERANK_REVISION} on {device} ...")
    t0 = time.time()
    _rerank_tokenizer = AutoTokenizer.from_pretrained(
        _RERANK_MODEL_ID,
        revision=_RERANK_REVISION,
        trust_remote_code=True,
    )
    _rerank_model = AutoModelForCausalLM.from_pretrained(
        _RERANK_MODEL_ID,
        torch_dtype=dt,
        revision=_RERANK_REVISION,
        trust_remote_code=True,
        **_offload_kwargs(gpu_cap_gib=4),
    ).eval()
    if not getattr(_rerank_model, "hf_device_map", None):
        _rerank_model = _rerank_model.to(device)
    print(f"[rerank] Loaded in {time.time() - t0:.1f}s")


def _score_prompt(prompt: str, max_length: int = _RERANK_MAX_LENGTH) -> float:
    inputs = _rerank_tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
    )
    inputs = _model_inputs(inputs, _rerank_model)

    with torch.inference_mode():
        outputs = _rerank_model.model(**inputs, use_cache=False)
        last_hidden = outputs.last_hidden_state[:, -1, :]
        logits = _rerank_model.lm_head(last_hidden)[0]

    token_true = _rerank_tokenizer.convert_tokens_to_ids("yes")
    token_false = _rerank_tokenizer.convert_tokens_to_ids("no")
    return (logits[token_true].float() - logits[token_false].float()).item()


def rerank_pairs(query, texts):
    prefix = '<|im_start|>system\nJudge whether the document is relevant to the search query. Answer only "yes" or "no".<|im_end|>\n'

    scores = []

    for text in texts:
        prompt = (
            prefix
            + f"<|im_start|>user\n<query>{query}</query>\n<document>{text}</document><|im_end|>\n"
            + "<|im_start|>assistant\n"
        )
        with torch.no_grad():
            try:
                scores.append(_score_prompt(prompt))
            except torch.OutOfMemoryError:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                scores.append(_score_prompt(prompt, max_length=2048))

    return scores


# ---- HTTP Handlers ----

class EmbedHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/embed":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                texts = body.get("inputs", [])
                result = embed_texts(texts)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as exc:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print(f"[embed] Request failed: {exc}", flush=True)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress logs


class RerankHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/rerank":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                query = body.get("query", "")
                texts = body.get("texts", [])
                scores = rerank_pairs(query, texts)
                # TEI format: list of {index, score}
                result = [{"index": i, "score": s} for i, s in enumerate(scores)]
                result.sort(key=lambda x: x["score"], reverse=True)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as exc:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print(f"[rerank] Request failed: {exc}", flush=True)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode())
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed-port", type=int, default=8081)
    parser.add_argument("--rerank-port", type=int, default=8082)
    parser.add_argument("--embed-only", action="store_true")
    parser.add_argument("--rerank-only", action="store_true")
    args = parser.parse_args()

    if not args.rerank_only:
        load_embed_model()
    if not args.embed_only:
        load_rerank_model()

    threads = []

    if not args.rerank_only:
        embed_server = ThreadingHTTPServer(("0.0.0.0", args.embed_port), EmbedHandler)
        t = threading.Thread(target=embed_server.serve_forever, daemon=True)
        t.start()
        threads.append(t)
        print(f"[embed] Serving on http://0.0.0.0:{args.embed_port}")

    if not args.embed_only:
        rerank_server = ThreadingHTTPServer(("0.0.0.0", args.rerank_port), RerankHandler)
        t = threading.Thread(target=rerank_server.serve_forever, daemon=True)
        t.start()
        threads.append(t)
        print(f"[rerank] Serving on http://0.0.0.0:{args.rerank_port}")

    print("\nReady! Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
