#!/usr/bin/env python3
"""
One-time script to generate KB-grounded client questions for E2E simulation.

Loads all KB sections via WIPON_KNOWLEDGE, sends each fact to LLM,
and collects 1-3 short questions per section.

Usage:
    python scripts/generate_kb_questions.py                # Default: 1 fact per LLM call
    python scripts/generate_kb_questions.py --batch 5      # Group 5 facts per call (faster)
    python scripts/generate_kb_questions.py --category pricing  # Only pricing category
    python scripts/generate_kb_questions.py --resume       # Continue from checkpoint
    python scripts/generate_kb_questions.py --dry-run      # Preview without LLM calls
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


PROMPT_TEMPLATE = """Ты помогаешь сгенерировать вопросы клиента для тестирования чат-бота.

Категория: {category}
Тема: {topic}
Факт:
{facts_text}

Сгенерируй 1-3 коротких вопроса (макс 15 слов каждый), которые реальный клиент
мог бы задать в чате, чтобы узнать эту информацию.
Пиши разговорным языком, как в мессенджере.

Формат ответа - только вопросы, по одному на строку:"""

# Phrases that indicate meta-text rather than a real question
META_PHRASES = [
    "вопрос:", "например:", "вот", "вариант:", "пример:",
    "ответ:", "вопросы:", "варианты:", "примеры:",
]

# Markdown/formatting chars to reject
MARKDOWN_CHARS = ["**", "•", "- ", "* ", "1.", "2.", "3."]


def truncate_facts(text: str, max_words: int = 300) -> str:
    """Truncate facts text to first max_words words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def validate_question(q: str) -> Tuple[bool, str]:
    """Validate a single generated question.

    Returns:
        (is_valid, reason) tuple
    """
    q = q.strip()

    if not q:
        return False, "empty"

    if not q.endswith("?"):
        return False, "no_question_mark"

    if len(q) < 5:
        return False, "too_short"

    if len(q) > 80:
        return False, "too_long"

    q_lower = q.lower()
    for phrase in META_PHRASES:
        if phrase in q_lower:
            return False, f"meta_phrase:{phrase}"

    for char in MARKDOWN_CHARS:
        if char in q:
            return False, f"markdown:{char}"

    return True, "ok"


def jaccard_similarity(a: str, b: str) -> float:
    """Calculate Jaccard similarity on word sets."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0


def dedup_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate questions by exact match + fuzzy similarity."""
    seen_exact: Set[str] = set()
    unique: List[Dict[str, Any]] = []

    for q in questions:
        text = q["text"].strip().lower()

        # Exact dedup
        if text in seen_exact:
            continue

        # Fuzzy dedup: check against all existing unique questions
        is_dup = False
        for existing in unique:
            if jaccard_similarity(text, existing["text"].lower()) > 0.7:
                is_dup = True
                break

        if not is_dup:
            seen_exact.add(text)
            unique.append(q)

    return unique


def load_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
    """Load checkpoint if exists."""
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_topics": [], "questions": [], "rejected": 0}


def save_checkpoint(checkpoint_path: str, data: Dict[str, Any]):
    """Save checkpoint data."""
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_questions_from_response(
    response: str,
    category: str,
    topic: str,
    priority: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Parse LLM response into validated questions.

    Returns:
        (valid_questions, rejected_count)
    """
    valid = []
    rejected = 0

    for line in response.strip().split("\n"):
        line = line.strip()
        # Remove numbering prefixes like "1. ", "1) "
        line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()

        if not line:
            continue

        is_valid, reason = validate_question(line)
        if is_valid:
            valid.append({
                "text": line,
                "category": category,
                "source_topic": topic,
                "priority": priority,
            })
        else:
            rejected += 1

    return valid, rejected


def generate_questions(
    llm,
    sections,
    batch_size: int = 1,
    category_filter: Optional[str] = None,
    resume: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Generate questions from KB sections.

    Args:
        llm: OllamaLLM instance
        sections: List of KnowledgeSection
        batch_size: Number of facts per LLM call
        category_filter: Only process this category
        resume: Continue from checkpoint
        dry_run: Preview without LLM calls

    Returns:
        Result dict with questions and metadata
    """
    data_dir = Path(__file__).resolve().parent.parent / "src" / "simulator" / "data"
    os.makedirs(data_dir, exist_ok=True)
    checkpoint_path = str(data_dir / "kb_questions_checkpoint.json")

    # Filter sections
    if category_filter:
        sections = [s for s in sections if s.category == category_filter]

    if not sections:
        print("No sections to process.")
        return {"questions": [], "total_generated": 0, "total_after_dedup": 0, "rejected": 0}

    print(f"Sections to process: {len(sections)}")

    # Load checkpoint if resuming
    checkpoint = load_checkpoint(checkpoint_path) if resume else {
        "processed_topics": [], "questions": [], "rejected": 0,
    }
    processed_topics = set(checkpoint["processed_topics"])
    all_questions = list(checkpoint["questions"])
    total_rejected = checkpoint["rejected"]

    # Group sections into batches
    remaining = [s for s in sections if s.topic not in processed_topics]
    print(f"Remaining after checkpoint: {len(remaining)}")

    if dry_run:
        print("\n[DRY RUN] Would process:")
        for s in remaining[:10]:
            facts_preview = truncate_facts(s.facts, 20)
            print(f"  {s.category}/{s.topic}: {facts_preview}")
        if len(remaining) > 10:
            print(f"  ... and {len(remaining) - 10} more")
        return {"questions": all_questions, "total_generated": len(all_questions),
                "total_after_dedup": len(all_questions), "rejected": total_rejected}

    # Process sections
    for i, section in enumerate(remaining):
        if batch_size > 1 and i % batch_size != 0:
            # In batch mode, we group N sections per call
            continue

        # Collect batch
        batch_end = min(i + batch_size, len(remaining))
        batch_sections = remaining[i:batch_end]

        for sec in batch_sections:
            facts_text = truncate_facts(sec.facts, 300)
            prompt = PROMPT_TEMPLATE.format(
                category=sec.category,
                topic=sec.topic,
                facts_text=facts_text,
            )

            try:
                response = llm.generate(prompt)
                questions, rejected = parse_questions_from_response(
                    response, sec.category, sec.topic, sec.priority,
                )
                all_questions.extend(questions)
                total_rejected += rejected
                processed_topics.add(sec.topic)

                if questions:
                    print(f"  [{len(processed_topics)}/{len(sections)}] "
                          f"{sec.category}/{sec.topic}: {len(questions)} questions")
                else:
                    print(f"  [{len(processed_topics)}/{len(sections)}] "
                          f"{sec.category}/{sec.topic}: 0 questions (rejected: {rejected})")

            except Exception as e:
                print(f"  ERROR {sec.category}/{sec.topic}: {e}")
                continue

        # Save checkpoint every 50 sections
        if len(processed_topics) % 50 == 0:
            save_checkpoint(checkpoint_path, {
                "processed_topics": list(processed_topics),
                "questions": all_questions,
                "rejected": total_rejected,
            })
            print(f"  [CHECKPOINT] {len(processed_topics)} sections, {len(all_questions)} questions")

        # Small delay to avoid overwhelming Ollama
        time.sleep(0.1)

    # Final checkpoint
    save_checkpoint(checkpoint_path, {
        "processed_topics": list(processed_topics),
        "questions": all_questions,
        "rejected": total_rejected,
    })

    # Dedup
    total_before_dedup = len(all_questions)
    all_questions = dedup_questions(all_questions)

    return {
        "questions": all_questions,
        "total_generated": total_before_dedup,
        "total_after_dedup": len(all_questions),
        "rejected": total_rejected,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate KB-grounded client questions")
    parser.add_argument("--batch", type=int, default=1,
                        help="Number of facts per LLM call (default: 1)")
    parser.add_argument("--category", type=str, default=None,
                        help="Only process specific category")
    parser.add_argument("--resume", action="store_true",
                        help="Continue from last checkpoint")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without LLM calls")
    args = parser.parse_args()

    print("=" * 60)
    print("KB Question Generator")
    print("=" * 60)

    # Load knowledge base
    print("Loading knowledge base...")
    from src.knowledge import WIPON_KNOWLEDGE
    sections = WIPON_KNOWLEDGE.sections
    print(f"Total KB sections: {len(sections)}")

    # Get unique categories
    categories = sorted(set(s.category for s in sections))
    print(f"Categories: {', '.join(categories)}")

    if args.dry_run:
        print("\n[DRY RUN MODE]")

    # Initialize LLM
    if not args.dry_run:
        print("Initializing Ollama...")
        from src.llm import OllamaLLM
        llm = OllamaLLM()

        # Warmup
        print("Warming up LLM...")
        try:
            llm.generate("привет")
            print("LLM ready")
        except Exception as e:
            print(f"ERROR: Could not connect to Ollama: {e}")
            sys.exit(1)
    else:
        llm = None

    print()

    # Generate
    result = generate_questions(
        llm=llm,
        sections=sections,
        batch_size=args.batch,
        category_filter=args.category,
        resume=args.resume,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("\n[DRY RUN] No output file generated.")
        return

    # Build output
    from src.settings import settings
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_generated": result["total_generated"],
        "total_after_dedup": result["total_after_dedup"],
        "rejected": result["rejected"],
        "model": settings.llm.model,
        "questions": result["questions"],
    }

    # Save
    output_path = Path(__file__).resolve().parent.parent / "src" / "simulator" / "data" / "kb_questions.json"
    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print("DONE")
    print(f"  Total generated: {result['total_generated']}")
    print(f"  After dedup:     {result['total_after_dedup']}")
    print(f"  Rejected:        {result['rejected']}")
    print(f"  Output:          {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
