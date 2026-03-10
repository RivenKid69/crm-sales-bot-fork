#!/usr/bin/env python3
"""
Читает pain_realistic_dialogs.txt, для каждого сообщения клиента
прогоняет retrieval (основная БЗ + боли) и вставляет цитаты [БЗ] / [БЗ боли]
между строкой клиента и ответом бота.

Запуск:
    python -m scripts.inject_kb_citations 2>/dev/null
"""

import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.knowledge.retriever import get_retriever
from src.knowledge.pain_retriever import retrieve_pain_context
from src.llm import OllamaLLM

INPUT = Path("results/pain_realistic_dialogs.txt")
OUTPUT = INPUT  # overwrite in-place


def clean_kb_snippet(facts: str, max_len: int = 400) -> str:
    """Strip headers/noise from retrieved_facts, keep content."""
    if not facts or not facts.strip():
        return ""
    lines = facts.split("\n")
    useful = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r'^\[.+/.+\]$', s):
            continue
        if s.startswith("===") and s.endswith("==="):
            continue
        if re.match(r'^(topic|priority|keywords|category)\s*:', s):
            continue
        if "response_context" in s.lower() and "empty" in s.lower():
            continue
        if s.lower().startswith("информация по этому вопросу будет уточнена"):
            continue
        useful.append(s)
    text = " ".join(useful)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def clean_pain_snippet(pain_ctx: str, max_len: int = 300) -> str:
    """Strip instruction headers from pain context."""
    if not pain_ctx or not pain_ctx.strip():
        return ""
    lines = pain_ctx.split("\n")
    useful = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("==="):
            continue
        if "вплети" in s.lower() or "не выделяй" in s.lower():
            continue
        useful.append(s)
    text = " ".join(useful)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def run():
    print("Injecting KB citations into pain_realistic_dialogs.txt ...", flush=True)

    retriever = get_retriever()
    llm = OllamaLLM()

    text = INPUT.read_text(encoding="utf-8")
    lines = text.split("\n")

    out = []
    i = 0
    msg_count = 0

    while i < len(lines):
        line = lines[i]

        # Detect "Клиент: ..." line
        if line.startswith("Клиент: "):
            user_msg = line[len("Клиент: "):]
            out.append(line)
            msg_count += 1

            # Run retrieval
            try:
                facts, _urls = retriever.retrieve_with_urls(user_msg)
            except Exception:
                facts = ""
            try:
                pain_ctx = retrieve_pain_context(user_msg, intent=None, llm=llm)
            except Exception:
                pain_ctx = ""

            kb_snip = clean_kb_snippet(facts)
            pain_snip = clean_pain_snippet(pain_ctx)

            if kb_snip or pain_snip:
                out.append("")
                if kb_snip:
                    out.append(f"    [БЗ] {kb_snip}")
                if pain_snip:
                    out.append(f"    [БЗ боли] {pain_snip}")
                out.append("")

            status = ""
            if kb_snip:
                status += f"БЗ={len(kb_snip)}ch "
            if pain_snip:
                status += f"боли={len(pain_snip)}ch"
            if not status:
                status = "пусто"
            print(f"  [{msg_count}] {user_msg[:50]}... → {status}", flush=True)

            i += 1
            continue

        out.append(line)
        i += 1

    OUTPUT.write_text("\n".join(out), encoding="utf-8")
    print(f"\nГотово: {OUTPUT} ({msg_count} сообщений обработано)", flush=True)


if __name__ == "__main__":
    run()
