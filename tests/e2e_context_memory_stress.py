#!/usr/bin/env python3
"""
E2E Stress Test: Dialog Context Memory & Retention.

Tests how the bot remembers and uses conversation context across turns.

Key areas tested:
  1. FACT RETENTION — facts mentioned early in conversation, checked later
  2. HISTORY WINDOW — what the model actually sees (4 vs 30 turns)
  3. EPISODIC MEMORY — pain_points, company data persistence in ContextWindow
  4. CONTEXT AFTER COMPACTION — what survives history_compact (and does it even get used?)
  5. LONG DIALOG DEGRADATION — quality over 15-20+ turn conversations
  6. REPETITION / DEDUP — does the bot avoid repeating itself in long dialogs

Usage:
  python tests/e2e_context_memory_stress.py                    # full run
  python tests/e2e_context_memory_stress.py --flow autonomous  # autonomous only
  python tests/e2e_context_memory_stress.py --flow spin_selling # spin only
  python tests/e2e_context_memory_stress.py --compact          # summary only
"""

import sys
import os
import time
import json
import re
import argparse
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaLLM
from src.bot import SalesBot
from src.context_window import ContextWindow


# ═══════════════════════════════════════════════════════════════════
# Test Scenario Definitions
# ═══════════════════════════════════════════════════════════════════

@dataclass
class FactMarker:
    """A specific fact injected into conversation to track retention."""
    name: str           # e.g. "company_name"
    value: str          # e.g. "НефтеТрансСервис"
    injected_at: int    # turn number where fact is introduced
    check_at: List[int] # turn numbers where we probe for this fact
    check_keywords: List[str]  # keywords to look for in bot response


@dataclass
class ConversationTurn:
    """A single user message in a scripted scenario."""
    message: str
    description: str = ""  # what this turn tests
    expect_in_response: List[str] = field(default_factory=list)  # keywords expected
    expect_not_in_response: List[str] = field(default_factory=list)  # should NOT appear
    is_probe: bool = False  # True if this turn probes for earlier context
    probe_fact: str = ""    # which fact we're probing for


@dataclass
class TurnResult:
    """Result of a single conversation turn."""
    turn_num: int
    user_message: str
    bot_response: str
    intent: str
    state: str
    description: str
    # History analysis
    history_len: int
    history_formatted_len: int  # chars in formatted history sent to LLM
    # Context window state
    cw_turns: int
    episodic_episodes: int
    episodic_pain_points: List[str]
    episodic_client_data: Dict[str, Any]
    # Fact checks
    fact_checks: Dict[str, bool] = field(default_factory=dict)  # fact_name -> found_in_response
    # Dedup
    similarity_to_prev: float = 0.0
    elapsed_ms: float = 0.0


@dataclass
class ScenarioResult:
    """Full result of a test scenario."""
    scenario_name: str
    flow_name: str
    turns: List[TurnResult]
    fact_markers: List[FactMarker]
    # Aggregates
    total_turns: int = 0
    facts_retained: int = 0
    facts_lost: int = 0
    total_elapsed_s: float = 0.0
    avg_response_len: float = 0.0
    dedup_violations: int = 0  # turns with high similarity to previous
    history_compact_used: bool = False  # was history_compact ever injected


# ═══════════════════════════════════════════════════════════════════
# Scenario 1: LONG B2B DIALOG with fact injection & probing
# ═══════════════════════════════════════════════════════════════════

SCENARIO_LONG_DIALOG = {
    "name": "Long B2B Dialog — 18 turns, fact retention stress",
    "description": """
    Simulates a realistic long B2B sales conversation.
    Injects specific facts at turns 1-5, then probes for them at turns 10-18.
    Tests: history window limits, episodic memory, context degradation.
    """,
    "fact_markers": [
        FactMarker("company_name", "НефтеТрансСервис", 1, [8, 12, 17], ["НефтеТрансСервис", "нефтетранс"]),
        FactMarker("employee_count", "450", 2, [10, 15], ["450"]),
        FactMarker("pain_point", "ручной учёт заявок в Excel", 3, [11, 16], ["excel", "ручной", "заявк"]),
        FactMarker("contact_name", "Алексей Петрович", 1, [9, 14], ["Алексей", "Петрович"]),
        FactMarker("budget_range", "2 миллиона рублей", 5, [13, 17], ["2 миллион", "2 млн", "бюджет"]),
    ],
    "turns": [
        # === TURN 1: greeting + inject company & contact ===
        ConversationTurn(
            message="Добрый день! Меня зовут Алексей Петрович, я из компании НефтеТрансСервис. Нам посоветовали ваш продукт.",
            description="Greeting + inject company_name + contact_name",
        ),
        # === TURN 2: inject employee count ===
        ConversationTurn(
            message="У нас в компании 450 сотрудников, работаем в логистике и транспорте нефтепродуктов.",
            description="Inject employee_count + industry",
        ),
        # === TURN 3: inject pain point ===
        ConversationTurn(
            message="Основная проблема — весь учёт заявок ведём в Excel вручную, постоянно теряются данные, дубли.",
            description="Inject pain_point (manual Excel tracking)",
        ),
        # === TURN 4: normal conversation ===
        ConversationTurn(
            message="Да, пробовали пару CRM раньше, но они были слишком сложные для наших ребят.",
            description="Additional context — previous CRM experience",
        ),
        # === TURN 5: inject budget ===
        ConversationTurn(
            message="Бюджет у нас где-то в районе 2 миллионов рублей на год, может чуть больше.",
            description="Inject budget_range",
        ),
        # === TURN 6-7: normal conversation (filler) ===
        ConversationTurn(
            message="Да, интересно. А как у вас с интеграцией с 1С? Это для нас критично.",
            description="Technical question (filler)",
        ),
        ConversationTurn(
            message="А мобильное приложение есть? Наши водители в разъездах постоянно.",
            description="Technical question (filler)",
        ),
        # === TURN 8: PROBE for company_name (distance=7) ===
        ConversationTurn(
            message="Так, давайте подытожим — что конкретно вы можете предложить для нашей компании?",
            description="PROBE: should mention НефтеТрансСервис (distance=7)",
            is_probe=True,
            probe_fact="company_name",
            expect_in_response=["НефтеТрансСервис"],
        ),
        # === TURN 9: PROBE for contact_name (distance=8) ===
        ConversationTurn(
            message="А можете ещё раз объяснить мне лично, какие преимущества именно для меня как руководителя?",
            description="PROBE: should address Алексей Петрович (distance=8)",
            is_probe=True,
            probe_fact="contact_name",
            expect_in_response=["Алексей"],
        ),
        # === TURN 10: PROBE for employee_count (distance=8) ===
        ConversationTurn(
            message="А у вас тариф зависит от количества пользователей? Сколько нам нужно лицензий?",
            description="PROBE: should reference 450 employees (distance=8)",
            is_probe=True,
            probe_fact="employee_count",
            expect_in_response=["450"],
        ),
        # === TURN 11: PROBE for pain_point (distance=8) ===
        ConversationTurn(
            message="Напомните, как именно ваш продукт решит наши текущие проблемы?",
            description="PROBE: should reference Excel/manual tracking (distance=8)",
            is_probe=True,
            probe_fact="pain_point",
            expect_in_response=["excel", "ручн"],
        ),
        # === TURN 12: second probe for company_name (distance=11) ===
        ConversationTurn(
            message="Хорошо, а есть кейсы из нашей отрасли? Чтобы мы могли сравнить.",
            description="PROBE: should reference our company/industry context (distance=11)",
            is_probe=True,
            probe_fact="company_name",
            expect_in_response=["логистик", "транспорт", "нефт"],
        ),
        # === TURN 13: PROBE for budget (distance=8) ===
        ConversationTurn(
            message="Давайте по деньгам — вписываемся в наш бюджет или нет?",
            description="PROBE: should reference 2 million budget (distance=8)",
            is_probe=True,
            probe_fact="budget_range",
            expect_in_response=["2 миллион", "2 млн", "бюджет"],
        ),
        # === TURN 14-15: more filler ===
        ConversationTurn(
            message="А сроки внедрения какие? Нам нужно запуститься до конца квартала.",
            description="Timeline question (filler)",
        ),
        ConversationTurn(
            message="Техподдержка у вас 24/7 или только в рабочее время?",
            description="Support question (filler)",
        ),
        # === TURN 16: late PROBE for pain_point (distance=13) ===
        ConversationTurn(
            message="Слушайте, а вот наша главная боль которую я описывал в начале — вы точно её решите?",
            description="PROBE: explicit reference to early pain_point (distance=13)",
            is_probe=True,
            probe_fact="pain_point",
            expect_in_response=["excel", "ручн", "заявк", "учёт"],
        ),
        # === TURN 17: late PROBE for all facts combined ===
        ConversationTurn(
            message="Ок, подготовьте мне краткое резюме нашего разговора — что мы обсудили, что решили.",
            description="PROBE: summary request — should reference ALL early facts",
            is_probe=True,
            probe_fact="summary_all",
            expect_in_response=["НефтеТрансСервис", "450", "Excel"],
        ),
    ],
}


# ═══════════════════════════════════════════════════════════════════
# Scenario 2: SESSION RESTORE — context after save/load
# ═══════════════════════════════════════════════════════════════════

SCENARIO_SESSION_RESTORE = {
    "name": "Session Restore — context survival after snapshot",
    "description": """
    Tests what happens to context when a conversation is saved to snapshot
    and then restored. Verifies that episodic memory, collected data,
    and history_compact survive the round-trip.
    """,
    "fact_markers": [
        FactMarker("company_name", "ТехноМаркет", 1, [7], ["ТехноМаркет", "техномаркет"]),
        FactMarker("pain_point", "потеря лидов из-за отсутствия CRM", 2, [7], ["лид", "потер", "crm"]),
    ],
    "turns": [
        ConversationTurn(
            message="Здравствуйте, я из компании ТехноМаркет, у нас интернет-магазин электроники.",
            description="Inject company_name",
        ),
        ConversationTurn(
            message="Наша проблема — постоянно теряем лиды, потому что нет нормальной CRM, всё в головах менеджеров.",
            description="Inject pain_point",
        ),
        ConversationTurn(
            message="В команде продаж у нас 25 человек.",
            description="More context",
        ),
        ConversationTurn(
            message="Да, пробовали Битрикс24, не подошёл — слишком перегруженный.",
            description="Previous experience",
        ),
        # === SAVE SNAPSHOT HERE (after turn 4) ===
        # === RESTORE FROM SNAPSHOT ===
        ConversationTurn(
            message="Так, на чём мы остановились? Расскажите что вы поняли о наших потребностях.",
            description="POST-RESTORE PROBE: should remember ТехноМаркет + pain (after restore)",
            is_probe=True,
            probe_fact="company_name",
            expect_in_response=["ТехноМаркет"],
        ),
        ConversationTurn(
            message="А что именно вы предлагаете для решения нашей проблемы с лидами?",
            description="POST-RESTORE PROBE: should remember pain_point (after restore)",
            is_probe=True,
            probe_fact="pain_point",
            expect_in_response=["лид", "потер"],
        ),
    ],
}


# ═══════════════════════════════════════════════════════════════════
# Scenario 3: REPETITION STRESS — does bot loop in long dialogs?
# ═══════════════════════════════════════════════════════════════════

SCENARIO_REPETITION = {
    "name": "Repetition Stress — dedup check over 12 turns",
    "description": """
    Tests if the bot starts repeating itself in a long conversation
    where the user asks similar (but not identical) questions.
    Measures Jaccard similarity between consecutive responses.
    """,
    "fact_markers": [],
    "turns": [
        ConversationTurn(message="Привет, расскажите о вашем продукте.", description="Initial question"),
        ConversationTurn(message="А какие есть основные функции?", description="Features question v1"),
        ConversationTurn(message="Интересно. А расскажите подробнее про возможности.", description="Features question v2 (similar)"),
        ConversationTurn(message="Хорошо, а ещё какой функционал есть?", description="Features question v3 (similar)"),
        ConversationTurn(message="Понятно. А какие ещё есть фичи которые вы не упомянули?", description="Features question v4 (similar)"),
        ConversationTurn(message="А чем вы лучше конкурентов?", description="Competition question v1"),
        ConversationTurn(message="А если сравнить с другими CRM — в чём преимущество?", description="Competition question v2 (similar)"),
        ConversationTurn(message="Почему именно вас стоит выбрать а не другое решение?", description="Competition question v3 (similar)"),
        ConversationTurn(message="Какие есть тарифы?", description="Pricing v1"),
        ConversationTurn(message="А сколько стоит? Есть бесплатный тариф?", description="Pricing v2 (similar)"),
        ConversationTurn(message="А цена за пользователя какая?", description="Pricing v3 (similar)"),
        ConversationTurn(message="Резюмируйте всё что вы мне рассказали.", description="Summary request"),
    ],
}


# ═══════════════════════════════════════════════════════════════════
# Analysis Utilities
# ═══════════════════════════════════════════════════════════════════

def jaccard_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard similarity between two texts (word-level)."""
    if not text1 or not text2:
        return 0.0
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union) if union else 0.0


def check_keywords(text: str, keywords: List[str]) -> Tuple[List[str], List[str]]:
    """Check which keywords are present/absent in text."""
    text_lower = text.lower()
    found = []
    missing = []
    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)
        else:
            missing.append(kw)
    return found, missing


def analyze_context_window(bot: SalesBot) -> Dict[str, Any]:
    """Extract context window state for analysis."""
    cw = bot.context_window
    em = cw.episodic_memory

    return {
        "cw_turns": len(cw.turns),
        "episodic_episodes": len(em.episodes),
        "episodic_total_turns": em.total_turns,
        "episodic_pain_points": list(em.client_profile.pain_points) if em.client_profile else [],
        "episodic_client_data": {
            "company_name": em.client_profile.company_name,
            "company_size": em.client_profile.company_size,
            "industry": em.client_profile.industry,
            "role": em.client_profile.role,
        } if em.client_profile else {},
        "episodic_all_objections": dict(em.all_objections),
        "episodic_successful_actions": dict(em.successful_actions),
        "episodic_failed_actions": dict(em.failed_actions),
        "first_objection_recorded": em._first_objection_recorded,
        "breakthrough_recorded": em._breakthrough_recorded,
    }


# ═══════════════════════════════════════════════════════════════════
# Test Runner
# ═══════════════════════════════════════════════════════════════════

def run_scenario(
    scenario: Dict[str, Any],
    flow_name: str,
    compact_output: bool = False,
    save_restore_after: Optional[int] = None,
) -> ScenarioResult:
    """Run a single test scenario."""
    name = scenario["name"]
    turns_def = scenario["turns"]
    fact_markers = scenario.get("fact_markers", [])

    print(f"\n{'=' * 80}")
    print(f"  SCENARIO: {name}")
    print(f"  Flow: {flow_name} | Turns: {len(turns_def)} | Fact markers: {len(fact_markers)}")
    print(f"{'=' * 80}")

    llm = OllamaLLM()
    bot = SalesBot(llm=llm, flow_name=flow_name, enable_tracing=True)

    result = ScenarioResult(
        scenario_name=name,
        flow_name=flow_name,
        turns=[],
        fact_markers=fact_markers,
        total_turns=len(turns_def),
    )

    prev_response = ""
    start_total = time.time()

    for i, turn_def in enumerate(turns_def):
        turn_num = i + 1

        # === SESSION SAVE/RESTORE ===
        if save_restore_after and turn_num == save_restore_after + 1:
            print(f"\n  {'─' * 70}")
            print(f"  ⟳ SNAPSHOT SAVE/RESTORE after turn {save_restore_after}")
            # Grab last N turns of history BEFORE snapshot (snapshot stores empty history)
            history_before = list(bot.history)
            tail_size = 4
            history_tail = history_before[-tail_size:] if len(history_before) >= tail_size else history_before

            snapshot = bot.to_snapshot(compact_history=True, history_tail_size=tail_size)
            # Show compact info
            hc = snapshot.get("history_compact")
            if hc:
                print(f"    history_compact keys: {list(hc.keys())}")
                for k, v in hc.items():
                    if isinstance(v, list):
                        print(f"      {k}: {v[:3]}{'...' if len(v) > 3 else ''}")
            else:
                print(f"    history_compact: None (not generated)")

            hc_meta = snapshot.get("history_compact_meta")
            if hc_meta:
                print(f"    compact_meta: compacted_turns={hc_meta.get('compacted_turns')}, tail_size={hc_meta.get('tail_size')}")

            print(f"    Full history before snapshot: {len(history_before)} turns")
            print(f"    History tail passed to restore: {len(history_tail)} turns")

            # Restore with explicit history_tail
            bot_restored = SalesBot.from_snapshot(snapshot, llm=llm, history_tail=history_tail)
            print(f"    Restored bot history: {len(bot_restored.history)} turns")
            print(f"    Restored bot history_compact: {'yes' if bot_restored.history_compact else 'no'}")
            print(f"    Restored CW episodes: {len(bot_restored.context_window.episodic_memory.episodes)}")
            bot = bot_restored
            print(f"  {'─' * 70}")

        # === Send message ===
        start = time.time()
        try:
            result_dict = bot.process(turn_def.message)
            response = result_dict.get("response", "[NO RESPONSE]")
        except Exception as e:
            response = f"[ERROR: {e}]"
        elapsed = (time.time() - start) * 1000

        # Extract state info
        current_state = bot.state_machine.state
        last_intent = bot.last_intent or "?"

        # Analyze context window
        cw_info = analyze_context_window(bot)

        # History analysis
        history_len = len(bot.history)
        # Approximate formatted history length
        formatted = bot.generator.format_history(
            bot.history,
            use_full=(flow_name == "autonomous"),
        )
        history_formatted_len = len(formatted)

        # Fact checks for probe turns
        fact_checks = {}
        if turn_def.is_probe and turn_def.expect_in_response:
            for kw in turn_def.expect_in_response:
                fact_checks[kw] = kw.lower() in response.lower()

        # Similarity to previous response
        sim = jaccard_similarity(response, prev_response)

        turn_result = TurnResult(
            turn_num=turn_num,
            user_message=turn_def.message,
            bot_response=response,
            intent=last_intent,
            state=current_state,
            description=turn_def.description,
            history_len=history_len,
            history_formatted_len=history_formatted_len,
            cw_turns=cw_info["cw_turns"],
            episodic_episodes=cw_info["episodic_episodes"],
            episodic_pain_points=cw_info["episodic_pain_points"],
            episodic_client_data=cw_info["episodic_client_data"],
            fact_checks=fact_checks,
            similarity_to_prev=sim,
            elapsed_ms=elapsed,
        )
        result.turns.append(turn_result)
        prev_response = response

        # === Print turn ===
        status = ""
        if turn_def.is_probe:
            found_kw, missing_kw = check_keywords(response, turn_def.expect_in_response)
            if not missing_kw:
                status = "✅ ALL FACTS FOUND"
                result.facts_retained += len(found_kw)
            elif found_kw:
                status = f"⚠️  PARTIAL ({len(found_kw)}/{len(turn_def.expect_in_response)})"
                result.facts_retained += len(found_kw)
                result.facts_lost += len(missing_kw)
            else:
                status = "❌ FACTS LOST"
                result.facts_lost += len(turn_def.expect_in_response)

        if sim > 0.65:
            result.dedup_violations += 1

        if not compact_output:
            print(f"\n  Turn {turn_num:2d} | {turn_def.description}")
            print(f"  {'─' * 70}")
            print(f"  User: {turn_def.message[:100]}{'...' if len(turn_def.message) > 100 else ''}")
            print(f"  Bot:  {response[:200]}{'...' if len(response) > 200 else ''}")
            print(f"  Intent: {last_intent} | State: {current_state} | {elapsed:.0f}ms")
            print(f"  History: {history_len} turns (formatted: {history_formatted_len} chars)")
            print(f"  CW: {cw_info['cw_turns']}/5 turns | Episodes: {cw_info['episodic_episodes']}")
            if cw_info["episodic_pain_points"]:
                print(f"  Pain points (episodic): {cw_info['episodic_pain_points']}")
            if cw_info["episodic_client_data"].get("company_name"):
                print(f"  Client data (episodic): {cw_info['episodic_client_data']}")
            if status:
                print(f"  >>> {status}")
                if turn_def.is_probe:
                    found_kw, missing_kw = check_keywords(response, turn_def.expect_in_response)
                    if missing_kw:
                        print(f"      Missing: {missing_kw}")
                    if found_kw:
                        print(f"      Found:   {found_kw}")
            if sim > 0.5:
                print(f"  Similarity to prev: {sim:.2f} {'⚠️ HIGH' if sim > 0.65 else ''}")
        else:
            probe_flag = f" {status}" if status else ""
            print(f"  T{turn_num:2d} | {last_intent:30s} | {current_state:20s} | {elapsed:5.0f}ms | hist={history_len:2d} fmt={history_formatted_len:5d}ch | cw={cw_info['cw_turns']} ep={cw_info['episodic_episodes']:2d}{probe_flag}")

    result.total_elapsed_s = time.time() - start_total
    result.avg_response_len = (
        sum(len(t.bot_response) for t in result.turns) / len(result.turns)
        if result.turns else 0
    )
    result.history_compact_used = bot.history_compact is not None

    return result


def print_summary(results: List[ScenarioResult]):
    """Print final summary across all scenarios."""
    print(f"\n{'═' * 80}")
    print(f"  FINAL SUMMARY")
    print(f"{'═' * 80}")

    total_retained = sum(r.facts_retained for r in results)
    total_lost = sum(r.facts_lost for r in results)
    total_probes = total_retained + total_lost
    total_dedup = sum(r.dedup_violations for r in results)

    for r in results:
        probes = r.facts_retained + r.facts_lost
        pct = (r.facts_retained / probes * 100) if probes else 0
        print(f"\n  {r.scenario_name} [{r.flow_name}]")
        print(f"    Turns: {r.total_turns} | Time: {r.total_elapsed_s:.1f}s | Avg response: {r.avg_response_len:.0f} chars")
        print(f"    Fact retention: {r.facts_retained}/{probes} ({pct:.0f}%)")
        print(f"    Dedup violations (Jaccard > 0.65): {r.dedup_violations}")
        print(f"    history_compact stored: {'yes' if r.history_compact_used else 'no'}")

    if total_probes:
        print(f"\n  {'─' * 70}")
        print(f"  OVERALL FACT RETENTION: {total_retained}/{total_probes} ({total_retained/total_probes*100:.0f}%)")
        print(f"  OVERALL DEDUP VIOLATIONS: {total_dedup}")

    # === Detailed per-marker analysis ===
    print(f"\n  {'─' * 70}")
    print(f"  FACT RETENTION BY DISTANCE (turns between injection and probe):")
    print(f"  {'─' * 70}")

    for r in results:
        if not r.fact_markers:
            continue
        print(f"\n  [{r.scenario_name} / {r.flow_name}]")
        for fm in r.fact_markers:
            for check_turn in fm.check_at:
                if check_turn > len(r.turns):
                    continue
                distance = check_turn - fm.injected_at
                turn_result = r.turns[check_turn - 1]
                # Check if any of the marker's keywords were found
                response_lower = turn_result.bot_response.lower()
                found = any(kw.lower() in response_lower for kw in fm.check_keywords)
                status = "✅" if found else "❌"
                print(f"    {status} {fm.name:20s} | injected@T{fm.injected_at} → checked@T{check_turn} (distance={distance:2d}) | history_window={turn_result.history_len}")

    # === Context Window / Episodic Memory analysis ===
    print(f"\n  {'─' * 70}")
    print(f"  EPISODIC MEMORY STATE AT KEY TURNS:")
    print(f"  {'─' * 70}")

    for r in results:
        if not r.turns:
            continue
        key_turns = [0, len(r.turns) // 2, len(r.turns) - 1]
        for idx in key_turns:
            t = r.turns[idx]
            print(f"\n  [{r.scenario_name}] Turn {t.turn_num}:")
            print(f"    CW turns: {t.cw_turns}/5 | Episodes: {t.episodic_episodes}")
            print(f"    Pain points: {t.episodic_pain_points or '(none)'}")
            cd = t.episodic_client_data
            if cd and cd.get("company_name"):
                print(f"    Client: company={cd.get('company_name')}, size={cd.get('company_size')}, industry={cd.get('industry')}")

    # === History window analysis ===
    print(f"\n  {'─' * 70}")
    print(f"  HISTORY WINDOW GROWTH:")
    print(f"  {'─' * 70}")
    for r in results:
        print(f"\n  [{r.scenario_name} / {r.flow_name}]")
        for t in r.turns:
            bar = "█" * min(t.history_formatted_len // 100, 50)
            print(f"    T{t.turn_num:2d}: history={t.history_len:2d} turns, formatted={t.history_formatted_len:5d} chars {bar}")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="E2E Context Memory Stress Test")
    parser.add_argument("--flow", default=None, help="Run only this flow (e.g., autonomous, spin_selling)")
    parser.add_argument("--compact", action="store_true", help="Compact output (summary per turn)")
    parser.add_argument("--scenario", default=None, help="Run only this scenario (long, restore, repeat)")
    parser.add_argument("--json", default=None, help="Save results to JSON file")
    args = parser.parse_args()

    flows = [args.flow] if args.flow else ["autonomous", "spin_selling"]
    scenarios = []

    if not args.scenario or args.scenario == "long":
        scenarios.append(("long", SCENARIO_LONG_DIALOG, None))
    if not args.scenario or args.scenario == "restore":
        scenarios.append(("restore", SCENARIO_SESSION_RESTORE, 4))  # save/restore after turn 4
    if not args.scenario or args.scenario == "repeat":
        scenarios.append(("repeat", SCENARIO_REPETITION, None))

    all_results = []

    for flow_name in flows:
        for (label, scenario, save_after) in scenarios:
            try:
                result = run_scenario(
                    scenario=scenario,
                    flow_name=flow_name,
                    compact_output=args.compact,
                    save_restore_after=save_after,
                )
                all_results.append(result)
            except Exception as e:
                print(f"\n  ❌ SCENARIO FAILED: {scenario['name']} [{flow_name}]")
                print(f"     Error: {e}")
                import traceback
                traceback.print_exc()

    print_summary(all_results)

    # Save JSON results
    if args.json:
        json_data = []
        for r in all_results:
            scenario_data = {
                "scenario": r.scenario_name,
                "flow": r.flow_name,
                "total_turns": r.total_turns,
                "facts_retained": r.facts_retained,
                "facts_lost": r.facts_lost,
                "dedup_violations": r.dedup_violations,
                "total_elapsed_s": r.total_elapsed_s,
                "avg_response_len": r.avg_response_len,
                "history_compact_used": r.history_compact_used,
                "turns": [
                    {
                        "turn": t.turn_num,
                        "user": t.user_message,
                        "bot": t.bot_response,
                        "intent": t.intent,
                        "state": t.state,
                        "history_len": t.history_len,
                        "history_formatted_len": t.history_formatted_len,
                        "cw_turns": t.cw_turns,
                        "episodic_episodes": t.episodic_episodes,
                        "episodic_pain_points": t.episodic_pain_points,
                        "episodic_client_data": t.episodic_client_data,
                        "fact_checks": t.fact_checks,
                        "similarity_to_prev": t.similarity_to_prev,
                        "elapsed_ms": t.elapsed_ms,
                    }
                    for t in r.turns
                ],
            }
            json_data.append(scenario_data)

        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"\n  Results saved to: {args.json}")

    # Final verdict
    total_probes = sum(r.facts_retained + r.facts_lost for r in all_results)
    total_retained = sum(r.facts_retained for r in all_results)
    if total_probes:
        retention_pct = total_retained / total_probes * 100
        if retention_pct >= 80:
            print(f"\n  🟢 VERDICT: Good context retention ({retention_pct:.0f}%)")
        elif retention_pct >= 50:
            print(f"\n  🟡 VERDICT: Moderate context retention ({retention_pct:.0f}%) — consider expanding history window")
        else:
            print(f"\n  🔴 VERDICT: Poor context retention ({retention_pct:.0f}%) — critical issues with context management")


if __name__ == "__main__":
    main()
