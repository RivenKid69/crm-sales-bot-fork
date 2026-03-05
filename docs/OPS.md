# OPS: Запуск и эксплуатация CRM Sales Bot

## Требования

- Python 3.11+
- Ollama 0.17+ (systemd service на порту 8080)
- GPU: RTX 5090 или аналог (VRAM 32GB+ для Q4_K_M 27B)
- Модель: Qwen 3.5 27B Q4_K_M (`qwen3.5:27b`)

## 1. Запуск Ollama

Ollama работает как systemd service с `OLLAMA_HOST=0.0.0.0:8080`.

```bash
# Проверить статус
systemctl status ollama

# Перезапустить если нужно
sudo systemctl restart ollama

# Проверить доступность
curl -s http://localhost:8080/api/tags | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['models']]"
```

Конфиг systemd: `/etc/systemd/system/ollama.service.d/override.conf`
```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:8080"
```

## 2. Запуск бота (интерактивный режим)

```bash
cd /home/corta/crm-sales-bot-fork

# Автономный flow (по умолчанию)
python3 -m src.bot --flow autonomous

# Команды в чате: /reset /status /metrics /lead /flags /quit
```

`--flow autonomous` автоматически активирует все флаги:
- `autonomous_flow` = True
- `response_factual_verifier` = True
- `response_boundary_validator` = True
- `response_boundary_llm_judge` = True
- `response_boundary_retry` = True
- `response_boundary_fallback` = True

## 3. Запуск e2e тестов

Все скрипты используют `setup_autonomous_pipeline()` из `src.bot` для единообразной активации флагов.

```bash
# Основные e2e прогоны
python3 -m scripts.full_e2e_40              # 40 сценариев, JSON+MD в results/
python3 -m scripts.full_sim_e2e_40          # 40 симулированных диалогов
python3 -m scripts.kb_accuracy_e2e_160      # 160 KB-вопросов
python3 -m scripts.deep_manual_audit_10     # 10 глубоких аудитов

# Целевые тесты
python3 -m scripts.pricing_deflection_e2e   # Тарифные дефлекции
python3 -m scripts.disambiguation_e2e       # Дисамбигуация
python3 -m scripts.semantic_relevance_e2e   # Семантическая релевантность

# Стресс-тесты
python3 -m scripts.post5_stress_10          # 10 стресс-сценариев

# Unit-тесты (без LLM, быстрые)
python3 -m pytest tests/ -x -q
```

Результаты сохраняются в `results/` с таймстемпами.

## 4. Конфигурация

### settings.yaml (основной конфиг)
```yaml
llm:
  model: "qwen3.5:27b"           # Модель Ollama
  base_url: "http://localhost:8080"  # Ollama systemd service
  api_format: "ollama"            # Native Ollama API (think: false)
  timeout: 120
```

### Ключевые параметры
| Файл | Что настраивает |
|------|----------------|
| `src/settings.yaml` | LLM, retriever, reranker, feature flags |
| `src/yaml_config/flows/autonomous/` | Автономный flow (states, phases) |
| `src/yaml_config/templates/autonomous/prompts.yaml` | Промпты генерации |
| `src/knowledge/data/*.yaml` | База знаний (KB) |

### Feature flags
Приоритет: `set_override()` > env `FF_FLAG_NAME` > `settings.yaml` > defaults.

## 5. Архитектура пайплайна (1 ход)

```
User message
  -> UnifiedClassifier (intent + data extraction)
  -> Blackboard Orchestrator (sources: AutonomousDecision, PriceQuestion, StallGuard, ...)
  -> EnhancedRetrievalPipeline (FRIDA embeddings + RRF fusion)
  -> Template selection (autonomous_respond / answer_with_pricing / ...)
  -> ResponseGenerator (Qwen 3.5 27B, think:false)
  -> FactualVerifier (same model, isolated check)
  -> ResponseBoundaryValidator (hallucination/boundary checks)
  -> Final response
```

## 6. Создание нового e2e скрипта

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

setup_autonomous_pipeline()
llm = OllamaLLM()
bot = SalesBot(llm, flow_name="autonomous")

bot.reset()
result = bot.process("Здравствуйте")
print(result["response"])
```

## 7. Troubleshooting

| Проблема | Решение |
|----------|---------|
| `model not found` | Проверить `ollama list`, имя модели в settings.yaml |
| Timeout 120s | Модель не загружена в VRAM, первый запрос медленный |
| `Empty content` | Qwen 3.5 thinking model: убедись что `api_format: "ollama"` (использует `think: false`) |
| `Circuit breaker open` | Ollama упала, `sudo systemctl restart ollama` |
| Stale flags | Используй `setup_autonomous_pipeline()` перед созданием SalesBot |

## 8. GPU мониторинг

```bash
nvidia-smi                    # Однократно
watch -n 1 nvidia-smi         # Мониторинг
```

Qwen 3.5 27B Q4_K_M: ~17GB VRAM, ~90% GPU utilization при inference.
