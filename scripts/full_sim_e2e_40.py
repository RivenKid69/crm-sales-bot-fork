"""
Full E2E Simulation — 40 complex dialogs via SimulationRunner.

Both client (ClientAgent) and bot (SalesBot) use the same Qwen3.5-27B
via llama-server (OpenAI-compatible API at localhost:8080).

Tests ALL recent patches:
  - Reasoning-first schema (AutonomousDecision)
  - Removed deterministic fast-tracks → LLM decides everything
  - OpenAI API format (llama-server)
  - Semantic relevance check (new LLM validator)
  - Dialog history in classifier (n_few_shot 5→12)
  - Simplified state goals (no hardcoded CLOSING instructions)
  - Temperature 0.05, num_predict 2048 for structured decisions
  - Extended factual intents

40 dialogs = 2 per persona (21 personas), round-robin.
All through autonomous flow, sequential (parallel=1) to avoid GPU contention.

Usage:
    python -m scripts.full_sim_e2e_40 2>/dev/null
"""

import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Quality checks per dialog
# ---------------------------------------------------------------------------

# Phrases that should NEVER appear in bot responses
BANNED_PHRASES = [
    "менеджер свяжется",
    "наш менеджер",
    "я свяжусь с вами",
    "99.9%",
    "uptime 99",
    "error",
    "traceback",
    "exception",
    "NoneType",
    "Traceback (most recent call last)",
]

# Patterns for hallucination detection
HALLUCINATION_PATTERNS = [
    (re.compile(r'компания\s*[«"]', re.IGNORECASE), "fabricated_client_name"),
    (re.compile(r'наш\s+клиент\s+из\s*[«"]', re.IGNORECASE), "fabricated_testimonial"),
    (re.compile(r'скидка\s+\d{2,}%', re.IGNORECASE), "fabricated_discount"),
    (re.compile(r'(?:контакт|телефон|номер)\s+менеджера\s*:\s*[+\d]', re.IGNORECASE), "manager_contact_giveout"),
    (re.compile(r'демо[\s-]*верси[яю]', re.IGNORECASE), "demo_mention"),
    (re.compile(r'тестовый\s+период\s+14\s+дней', re.IGNORECASE), "wrong_trial_duration"),
]

# States that count as successful closing
TERMINAL_STATES = {"payment_ready", "video_call_scheduled"}
CLOSING_STATES = {"autonomous_closing"} | TERMINAL_STATES


def check_dialog(result) -> dict:
    """Run quality checks on a single simulation result."""
    issues = []
    warnings = []

    dialogue = result.dialogue
    if not dialogue:
        issues.append("EMPTY_DIALOG: No turns recorded")
        return {"issues": issues, "warnings": warnings}

    # Concatenate all bot responses
    all_bot = " ".join(t.get("bot", "") for t in dialogue)
    all_bot_lower = all_bot.lower()

    # 1. Banned phrases
    for phrase in BANNED_PHRASES:
        if phrase.lower() in all_bot_lower:
            for t in dialogue:
                if phrase.lower() in t.get("bot", "").lower():
                    issues.append(
                        f"BANNED_PHRASE: '{phrase}' at turn {t['turn']}: "
                        f"«{t['bot'][:150]}»"
                    )
                    break

    # 2. Hallucination patterns
    for pattern, label in HALLUCINATION_PATTERNS:
        for t in dialogue:
            bot_text = t.get("bot", "")
            if pattern.search(bot_text):
                issues.append(
                    f"HALLUCINATION[{label}] at turn {t['turn']}: "
                    f"«{bot_text[:150]}»"
                )
                break

    # 3. Question repetition (same SPIN question asked 2+ times)
    bot_questions = []
    question_re = re.compile(r'([^.!?]*\?)')
    for t in dialogue:
        bot_text = t.get("bot", "")
        for m in question_re.finditer(bot_text):
            q = m.group(1).strip().lower()
            if len(q) > 15:  # skip trivial questions
                bot_questions.append((t["turn"], q))

    # Check for near-duplicate questions
    seen_q = {}
    for turn_num, q in bot_questions:
        # Normalize: remove articles, extra spaces
        q_norm = re.sub(r'\s+', ' ', q)
        for prev_q, prev_turn in seen_q.items():
            # Simple overlap check
            if (
                len(q_norm) > 20
                and len(prev_q) > 20
                and (q_norm in prev_q or prev_q in q_norm)
                and abs(turn_num - prev_turn) >= 2
            ):
                warnings.append(
                    f"REPEATED_QUESTION: turn {prev_turn} → {turn_num}: «{q_norm[:80]}»"
                )
                break
        seen_q[q_norm] = turn_num

    # 4. State progression (should reach at least qualification if 5+ turns)
    states_visited = set()
    for t in dialogue:
        s = t.get("state", "")
        if s:
            states_visited.add(s)
        for vs in t.get("visited_states", []):
            if vs:
                states_visited.add(vs)

    n_turns = len(dialogue)
    autonomous_states = {s for s in states_visited if s.startswith("autonomous_")}

    if n_turns >= 6 and len(autonomous_states) <= 1:
        warnings.append(
            f"STUCK_IN_STATE: {n_turns} turns but only states: {autonomous_states}"
        )

    # 5. Empty responses
    for t in dialogue:
        if not t.get("bot", "").strip():
            issues.append(f"EMPTY_RESPONSE at turn {t['turn']}")

    # 6. Very short responses (< 10 chars) after discovery
    for t in dialogue:
        bot_text = t.get("bot", "").strip()
        if t["turn"] > 2 and len(bot_text) < 10 and bot_text:
            warnings.append(
                f"VERY_SHORT_RESPONSE at turn {t['turn']}: «{bot_text}»"
            )

    # 7. Errors
    for err in (result.errors or []):
        issues.append(f"ERROR: {err[:200]}")

    return {"issues": issues, "warnings": warnings}


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(results: list, checks_map: dict, duration_total: float) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Full Sim E2E 40 — {ts}\n"]
    lines.append(f"**Total duration**: {duration_total:.0f}s ({duration_total/60:.1f}min)\n")

    # Overall stats
    total = len(results)
    pass_count = sum(1 for r in results if not checks_map[r.simulation_id]["issues"])
    warn_count = sum(1 for r in results if checks_map[r.simulation_id]["warnings"])

    lines.append(f"## Overall: {pass_count}/{total} PASS ({warn_count} with warnings)\n")

    # Outcome breakdown
    outcomes = defaultdict(int)
    for r in results:
        outcomes[r.outcome] += 1
    lines.append("### Outcomes")
    lines.append("| Outcome | Count | % |")
    lines.append("|---------|-------|---|")
    for outcome, cnt in sorted(outcomes.items(), key=lambda x: -x[1]):
        lines.append(f"| {outcome} | {cnt} | {cnt*100//total}% |")
    lines.append("")

    # Per-persona breakdown
    lines.append("### Per-Persona Results")
    lines.append("| Persona | Outcome | Turns | Final State | Issues | Time(s) |")
    lines.append("|---------|---------|-------|-------------|--------|---------|")
    for r in results:
        c = checks_map[r.simulation_id]
        status = "FAIL" if c["issues"] else ("WARN" if c["warnings"] else "PASS")
        final_state = r.dialogue[-1]["state"] if r.dialogue else "?"
        lines.append(
            f"| {r.persona} | {r.outcome} ({status}) | {r.turns} | "
            f"{final_state} | {len(c['issues'])}E/{len(c['warnings'])}W | "
            f"{r.duration_seconds:.1f} |"
        )
    lines.append("")

    # Phase coverage
    phase_counts = defaultdict(int)
    for r in results:
        for phase in r.phases_reached:
            phase_counts[phase] += 1
    lines.append("### Phase Coverage")
    lines.append("| Phase | Reached | % |")
    lines.append("|-------|---------|---|")
    for phase in ["discovery", "qualification", "presentation",
                   "objection_handling", "negotiation", "closing"]:
        cnt = phase_counts.get(phase, 0)
        lines.append(f"| {phase} | {cnt}/{total} | {cnt*100//total}% |")
    lines.append(f"\n**Avg SPIN coverage**: {sum(r.spin_coverage for r in results)/total:.2f}\n")

    # Failures detail
    failed = [(r, checks_map[r.simulation_id]) for r in results if checks_map[r.simulation_id]["issues"]]
    if failed:
        lines.append("## Failures\n")
        for r, c in failed:
            lines.append(f"### #{r.simulation_id} [{r.persona}] — {r.outcome}")
            for issue in c["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

    # Warnings detail
    warned = [(r, checks_map[r.simulation_id]) for r in results
              if checks_map[r.simulation_id]["warnings"] and not checks_map[r.simulation_id]["issues"]]
    if warned:
        lines.append("## Warnings\n")
        for r, c in warned:
            lines.append(f"### #{r.simulation_id} [{r.persona}] — {r.outcome}")
            for w in c["warnings"]:
                lines.append(f"- {w}")
            lines.append("")

    # Full dialogs
    lines.append("## Full Dialogs\n")
    for r in results:
        c = checks_map[r.simulation_id]
        status = "FAIL" if c["issues"] else ("WARN" if c["warnings"] else "PASS")
        lines.append(f"---\n### #{r.simulation_id} [{r.persona}] {status} — {r.outcome} ({r.turns} turns, {r.duration_seconds:.1f}s)")
        lines.append(f"Phases: {r.phases_reached} | SPIN coverage: {r.spin_coverage:.2f}")
        if r.collected_data:
            lines.append(f"Collected: {r.collected_data}")
        lines.append("")

        for t in r.dialogue:
            lines.append(f"**C{t['turn']}:** {t.get('client', '')}")
            bot_preview = t.get("bot", "")[:500]
            lines.append(f"**B{t['turn']}:** {bot_preview}")
            lines.append(
                f"  `[{t.get('state', '')}] intent={t.get('intent', '')} "
                f"action={t.get('action', '')}`"
            )
            lines.append("")

        if c["issues"]:
            lines.append("**Issues:**")
            for issue in c["issues"]:
                lines.append(f"- {issue}")
        if c["warnings"]:
            lines.append("**Warnings:**")
            for w in c["warnings"]:
                lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaClient
    from src.simulator.runner import SimulationRunner
    from src.simulator.personas import get_all_persona_names

    setup_autonomous_pipeline()

    # Single LLM for both bot and client — Qwen3.5-27B via llama-server
    llm = OllamaClient()

    # 40 dialogs, 2 per persona (21 personas = 42, take first 40 round-robin)
    all_personas = get_all_persona_names()
    n_dialogs = 40

    # Build persona queue: 2x each, truncated to 40
    persona_queue = (all_personas * 2)[:n_dialogs]

    runner = SimulationRunner(
        bot_llm=llm,
        client_llm=llm,  # Same LLM for client
        verbose=True,
        flow_name="autonomous",
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)

    print(f"\n{'='*70}")
    print(f"Full Sim E2E 40 — {ts}")
    print(f"LLM: {llm.model} @ {llm.base_url} (api_format={llm.api_format})")
    print(f"Personas: {len(all_personas)} × 2 = {n_dialogs} dialogs")
    print(f"Flags: verifier=ON boundary=ON llm_judge=ON semantic_relevance=ON")
    print(f"{'='*70}\n")

    start_total = time.time()

    # Run sequentially (parallel=1) to avoid GPU contention on single llama-server
    results = []
    for i, persona_name in enumerate(persona_queue):
        print(f"\n  [{i+1}/{n_dialogs}] {persona_name} ...", flush=True)
        try:
            result = runner.run_single(persona_name)
            result.simulation_id = i
            results.append(result)

            final_state = result.dialogue[-1]["state"] if result.dialogue else "?"
            print(
                f"    → {result.outcome} | {result.turns} turns | "
                f"state={final_state} | {result.duration_seconds:.1f}s",
                flush=True,
            )
        except Exception as e:
            print(f"    → CRASH: {e}", flush=True)
            from src.simulator.runner import SimulationResult
            results.append(SimulationResult(
                simulation_id=i,
                persona=persona_name,
                outcome="crash",
                turns=0,
                duration_seconds=0.0,
                dialogue=[],
                errors=[str(e)],
            ))

    duration_total = time.time() - start_total

    # Run quality checks
    checks_map = {}
    for r in results:
        checks_map[r.simulation_id] = check_dialog(r)

    # Save JSON
    json_path = results_dir / f"full_sim_e2e_40_{ts}.json"
    json_data = {
        "timestamp": ts,
        "duration_total_s": round(duration_total, 1),
        "llm_model": llm.model,
        "llm_base_url": llm.base_url,
        "llm_api_format": llm.api_format,
        "n_dialogs": n_dialogs,
        "dialogs": [],
    }
    for r in results:
        c = checks_map[r.simulation_id]
        json_data["dialogs"].append({
            "id": r.simulation_id,
            "persona": r.persona,
            "outcome": r.outcome,
            "turns": r.turns,
            "duration_s": round(r.duration_seconds, 1),
            "phases_reached": r.phases_reached,
            "spin_coverage": round(r.spin_coverage, 3),
            "collected_data": r.collected_data,
            "final_state": r.dialogue[-1]["state"] if r.dialogue else "",
            "issues": c["issues"],
            "warnings": c["warnings"],
            "errors": r.errors,
            "dialogue": [
                {
                    "turn": t["turn"],
                    "client": t.get("client", ""),
                    "bot": t.get("bot", ""),
                    "state": t.get("state", ""),
                    "intent": t.get("intent", ""),
                    "action": t.get("action", ""),
                }
                for t in r.dialogue
            ],
        })

    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save markdown report
    md_path = results_dir / f"full_sim_e2e_40_{ts}.md"
    report = build_report(results, checks_map, duration_total)
    md_path.write_text(report, encoding="utf-8")

    # Print summary
    pass_count = sum(1 for r in results if not checks_map[r.simulation_id]["issues"])
    warn_count = sum(1 for r in results if checks_map[r.simulation_id]["warnings"])

    outcomes = defaultdict(int)
    for r in results:
        outcomes[r.outcome] += 1

    print(f"\n{'='*70}")
    print(f"RESULT: {pass_count}/{n_dialogs} PASS ({warn_count} with warnings)")
    print(f"Duration: {duration_total:.0f}s ({duration_total/60:.1f}min)")
    print()
    print("Outcomes:")
    for outcome, cnt in sorted(outcomes.items(), key=lambda x: -x[1]):
        print(f"  {outcome}: {cnt} ({cnt*100//n_dialogs}%)")
    print()

    # Per-persona summary
    persona_outcomes = defaultdict(list)
    for r in results:
        c = checks_map[r.simulation_id]
        status = "FAIL" if c["issues"] else "PASS"
        persona_outcomes[r.persona].append(f"{r.outcome}({status})")
    print("Per-persona:")
    for persona in sorted(persona_outcomes.keys()):
        print(f"  {persona}: {', '.join(persona_outcomes[persona])}")

    # Failures
    failed = [r for r in results if checks_map[r.simulation_id]["issues"]]
    if failed:
        print(f"\nFailed dialogs ({len(failed)}):")
        for r in failed:
            c = checks_map[r.simulation_id]
            print(f"  #{r.simulation_id} [{r.persona}]: {c['issues'][0][:100]}")

    print(f"\nReport: {md_path}")
    print(f"JSON:   {json_path}")
    print(f"{'='*70}")

    sys.exit(0 if pass_count >= 30 else 1)  # Allow up to 25% failures


if __name__ == "__main__":
    main()
