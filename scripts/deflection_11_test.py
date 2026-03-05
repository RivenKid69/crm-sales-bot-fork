#!/usr/bin/env python3
"""
Deflection test — 11 вопросов, на которые бот deflects вместо ответа.
Прогоняет через полный autonomous pipeline и собирает ПОЛНЫЙ e2e трейс:
  - retrieved_facts (какие факты из БЗ попали в промпт)
  - fact_keys (ключи KB секций)
  - selected_template_key (какой шаблон выбран)
  - reason_codes (deflection retry/fallback/guard)
  - prompt (финальный промпт, отправленный в LLM)
  - factual_verifier результат
  - validation_events (пост-процессор)
"""
import sys, os, json, re, time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaClient

DEFLECTION_PATTERNS = [
    r"расскажите\s+подробнее\s+о\s+ваш",
    r"какой\s+у\s+вас\s+бизнес",
    r"подберу\s+подходящий",
    r"уточните\s+ваш\s+запрос",
    r"расскажите.*что\s+вас\s+интересует",
    r"чем\s+.*могу\s+помочь",
]

TESTS = [
    {
        "id": 1,
        "question": "Чем отличаются сканеры WP930Z и WPB930?",
        "category": "equipment",
        "must_contain_any": ["WP930Z", "проводн", "10 000", "10000", "WPB930", "беспроводн", "17 000", "17000"],
    },
    {
        "id": 2,
        "question": "Как быстро можно подключить ТИС?",
        "category": "tis",
        "must_contain_any": ["1-2 дн", "1–2 дн", "один-два", "ЭЦП", "удалённо", "удаленно", "день", "дня", "дней"],
    },
    {
        "id": 3,
        "question": "Сколько времени занимает подключение Wipon?",
        "category": "support",
        "must_contain_any": ["час", "дн", "минут", "быстр"],
    },
    {
        "id": 4,
        "question": "Где находятся офисы Wipon?",
        "category": "delivery",
        "must_contain_any": ["Астан", "Алматы", "Шымкент", "офис", "город"],
    },
    {
        "id": 5,
        "question": "Доставляете ли в сёла и отдалённые населённые пункты?",
        "category": "delivery",
        "must_contain_any": ["да", "доставля", "Казахстан", "населённ", "населенн", "по всему", "курьер"],
    },
    {
        "id": 6,
        "question": "С какими банками работают POS-терминалы?",
        "category": "integrations",
        "must_contain_any": ["Forte", "Halyk", "Kaspi", "банк"],
    },
    {
        "id": 7,
        "question": "Поддерживает ли Wipon бесконтактную оплату NFC?",
        "category": "integrations",
        "must_contain_any": ["NFC", "бесконтактн", "поддерж", "да"],
    },
    {
        "id": 8,
        "question": "Нужна ли ЭЦП для подключения онлайн-кассы?",
        "category": "fiscal",
        "must_contain_any": ["нужна", "ЭЦП", "электронн", "подпис"],
    },
    {
        "id": 9,
        "question": "Можно ли смотреть аналитику в реальном времени?",
        "category": "analytics",
        "must_contain_any": ["реальн", "онлайн", "мониторинг", "дашборд", "панел"],
    },
    {
        "id": 10,
        "question": "Касса сама применит скидку при продаже?",
        "category": "promotions",
        "must_contain_any": ["автоматическ", "скидк", "акци", "касс", "да"],
    },
    {
        "id": 11,
        "question": "Чем Wipon лучше конкурентов?",
        "category": "competitors",
        "must_contain_any": ["облачн", "ТИС", "Kaspi", "интеграц", "преимущ"],
    },
]


def is_deflection(text: str) -> bool:
    text_lower = text.lower()
    for pat in DEFLECTION_PATTERNS:
        if re.search(pat, text_lower):
            return True
    return False


def check_keywords(text: str, keywords: list[str]) -> list[str]:
    found = []
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)
    return found


def patch_llm_for_prompt_capture(llm):
    """Monkey-patch llm.generate чтобы перехватить финальный промпт."""
    llm._captured_prompts = []
    original_generate = llm.generate

    def capturing_generate(prompt, **kwargs):
        llm._captured_prompts.append(prompt)
        return original_generate(prompt, **kwargs)

    llm.generate = capturing_generate
    return llm


def extract_trace(bot, resp):
    """Извлечь полный e2e трейс из bot после process()."""
    trace = {}

    # 1. reason_codes — содержат deflection retry/fallback маркеры
    trace["reason_codes"] = resp.get("reason_codes", [])

    # 2. resolution_trace — blackboard resolver
    trace["resolution_trace"] = resp.get("resolution_trace", {})

    # 3. decision_trace (enable_tracing=True)
    dt = resp.get("decision_trace")
    if dt:
        trace["decision_trace"] = dt

    # 4. generator meta — template, fact_keys, verifier
    try:
        meta = bot.generator.get_last_generation_meta()
        trace["selected_template_key"] = meta.get("selected_template_key", "?")
        trace["fact_keys"] = meta.get("fact_keys", [])
        trace["factual_verifier_verdict"] = meta.get("factual_verifier_verdict", "?")
        trace["factual_verifier_changed"] = meta.get("factual_verifier_changed", False)
        trace["validation_events"] = meta.get("validation_events", [])
    except Exception as e:
        trace["generator_meta_error"] = str(e)

    # 5. retrieved_facts — из blackboard response context
    try:
        rc = bot._orchestrator.blackboard.get_response_context()
        if rc:
            trace["retrieved_facts"] = rc.get("retrieved_facts", "")
            # Извлекаем question_instruction из variables
            variables = rc.get("variables", {})
            trace["question_instruction"] = variables.get("question_instruction", "")
            trace["state_gated_rules"] = variables.get("state_gated_rules", "")
            trace["address_instruction"] = variables.get("address_instruction", "")
        else:
            trace["retrieved_facts"] = "(response_context empty)"
    except Exception as e:
        trace["retrieved_facts_error"] = str(e)

    # 6. captured prompts (from monkey-patched llm)
    try:
        prompts = bot.generator.llm._captured_prompts
        # Берём последний промпт (тот что для тестового вопроса, не warmup)
        if prompts:
            trace["last_prompt"] = prompts[-1]
            trace["total_prompts_in_turn"] = len(prompts)
    except Exception:
        pass

    return trace


def run_test(label: str):
    llm = OllamaClient()
    patch_llm_for_prompt_capture(llm)

    results = []
    pass_count = 0
    deflection_count = 0

    print(f"\n{'='*60}")
    print(f"  DEFLECTION TEST + TRACE — {label}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    for i, tc in enumerate(TESTS):
        setup_autonomous_pipeline()
        bot = SalesBot(llm, flow_name="autonomous", enable_tracing=True)
        # Warm up — 2 сообщения чтобы надёжно выйти из greeting
        try:
            r1 = bot.process("Привет")
            s1 = r1.get("state", "")
            if "greeting" in s1:
                bot.process("Хочу узнать про Wipon")
        except Exception:
            pass

        # Сброс captured prompts перед тестовым вопросом
        llm._captured_prompts = []

        # Отправляем тестовый вопрос
        t0 = time.time()
        trace = {}
        try:
            resp = bot.process(tc["question"])
            elapsed = time.time() - t0
            answer = resp.get("response", "")
            state = resp.get("state", "?")
            intent = resp.get("intent", "?")
            action = resp.get("action", "?")
            trace = extract_trace(bot, resp)
        except Exception as e:
            elapsed = time.time() - t0
            answer = f"ERROR: {e}"
            state = intent = action = "error"

        defl = is_deflection(answer)
        found_kw = check_keywords(answer, tc["must_contain_any"])
        passed = len(found_kw) > 0 and not defl

        if passed:
            pass_count += 1
        if defl:
            deflection_count += 1

        status = "✅ PASS" if passed else ("🔴 DEFLECTION" if defl else "❌ FAIL")
        print(f"[{i+1:2d}/11] {status} | {tc['question'][:50]}")
        print(f"         Ответ: {answer[:150]}")
        print(f"         State={state} Intent={intent} Action={action} T={elapsed:.1f}s")
        print(f"         Template={trace.get('selected_template_key', '?')}")
        print(f"         FactKeys={trace.get('fact_keys', [])}")

        # Для FAIL/DEFLECTION — детальный вывод
        if not passed:
            print(f"         Keywords found: {found_kw} / needed: {tc['must_contain_any']}")
            rc = trace.get("reason_codes", [])
            if rc:
                print(f"         ReasonCodes: {rc}")
            rf = trace.get("retrieved_facts", "")
            if rf:
                # Показываем первые 300 символов фактов
                print(f"         RetrievedFacts (first 300): {rf[:300]}")
            qi = trace.get("question_instruction", "")
            if qi:
                print(f"         QuestionInstruction: {qi[:200]}")
        print()

        results.append({
            "id": tc["id"],
            "question": tc["question"],
            "category": tc["category"],
            "response": answer,
            "state": state,
            "intent": intent,
            "action": action,
            "is_deflection": defl,
            "keywords_found": found_kw,
            "keywords_expected": tc["must_contain_any"],
            "passed": passed,
            "elapsed_s": round(elapsed, 1),
            "trace": {
                "selected_template_key": trace.get("selected_template_key", "?"),
                "fact_keys": trace.get("fact_keys", []),
                "retrieved_facts": trace.get("retrieved_facts", ""),
                "question_instruction": trace.get("question_instruction", ""),
                "state_gated_rules": trace.get("state_gated_rules", ""),
                "reason_codes": trace.get("reason_codes", []),
                "factual_verifier_verdict": trace.get("factual_verifier_verdict", "?"),
                "factual_verifier_changed": trace.get("factual_verifier_changed", False),
                "validation_events": trace.get("validation_events", []),
                "last_prompt": trace.get("last_prompt", ""),
                "total_prompts_in_turn": trace.get("total_prompts_in_turn", 0),
            },
        })

    print(f"\n{'='*60}")
    print(f"  ИТОГО: {pass_count}/11 PASS, {deflection_count}/11 deflections")
    print(f"{'='*60}\n")

    return {
        "label": label,
        "timestamp": datetime.now().isoformat(),
        "pass_count": pass_count,
        "total": 11,
        "deflection_count": deflection_count,
        "results": results,
    }


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "trace"
    data = run_test(label)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"results/deflection_11_{label}_{ts}.json"
    os.makedirs("results", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
