"""Configuration for Knowledge Extractor."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class LLMConfig:
    """LLM configuration for Ollama."""
    base_url: str = "http://localhost:11434"  # Ollama default port
    model: str = "qwen3:14b"  # Ollama model name
    timeout: int = 120
    max_retries: int = 3
    temperature: float = 0.3
    max_tokens: int = 1024  # Conservative default for small models


@dataclass
class ChunkingConfig:
    """Chunking configuration."""
    min_chunk_size: int = 200
    max_chunk_size: int = 1500
    overlap_sentences: int = 2
    # For tables
    table_rows_per_chunk: int = 20
    # For messenger
    message_gap_minutes: int = 60


@dataclass
class ExtractionConfig:
    """Extraction configuration."""
    min_keywords: int = 20
    max_keywords: int = 50
    min_facts_length: int = 50
    default_priority: int = 8


@dataclass
class DeduplicationConfig:
    """Deduplication configuration."""
    similarity_threshold: float = 0.85
    embedder_model: str = "ai-forever/ru-en-RoSBERTa"


@dataclass
class OutputConfig:
    """Output configuration."""
    company_name: Optional[str] = None
    company_description: Optional[str] = None


# Category mappings (from crm_sales_bot)
CATEGORIES = [
    "analytics",
    "competitors",
    "employees",
    "equipment",
    "faq",
    "features",
    "fiscal",
    "integrations",
    "inventory",
    "mobile",
    "pricing",
    "products",
    "promotions",
    "regions",
    "stability",
    "support",
    "tis",
]

CATEGORY_FILES = {cat: f"{cat}.yaml" for cat in CATEGORIES}

# Keywords hints for category routing
CATEGORY_KEYWORDS = {
    "pricing": [
        "тариф", "цена", "стоимость", "прайс", "оплата", "подписка",
        "бесплатно", "скидка", "акция", "рассрочка", "платёж", "стоит",
    ],
    "features": [
        "функция", "возможность", "работает", "поддерживает", "позволяет",
        "автоматически", "настройка", "интерфейс", "опция",
    ],
    "integrations": [
        "интеграция", "подключение", "api", "1с", "kaspi", "telegram",
        "whatsapp", "банк", "терминал", "эквайринг", "синхронизация",
    ],
    "support": [
        "поддержка", "помощь", "обучение", "консультация", "техподдержка",
        "настройка", "установка", "внедрение", "служба",
    ],
    "equipment": [
        "оборудование", "касса", "сканер", "принтер", "терминал",
        "устройство", "ккм", "фискальный", "железо", "hardware",
    ],
    "mobile": [
        "мобильное", "приложение", "телефон", "смартфон", "android",
        "ios", "app", "мобильный",
    ],
    "products": [
        "продукт", "wipon", "решение", "система", "программа", "сервис",
    ],
    "analytics": [
        "аналитика", "отчёт", "статистика", "график", "анализ", "метрика",
    ],
    "inventory": [
        "склад", "товар", "остаток", "приёмка", "списание", "инвентаризация",
    ],
    "employees": [
        "сотрудник", "кадры", "зарплата", "персонал", "доступ", "роль",
    ],
    "faq": [
        "вопрос", "faq", "часто", "можно ли", "работает ли", "как",
    ],
    "stability": [
        "стабильность", "безопасность", "защита", "шифрование", "бэкап",
    ],
    "competitors": [
        "конкурент", "сравнение", "альтернатива", "отличие", "преимущество",
    ],
    "fiscal": [
        "фискальный", "офд", "чек", "налог", "касса", "фискализация",
    ],
    "regions": [
        "регион", "город", "доставка", "казахстан", "алматы", "астана",
    ],
    "promotions": [
        "акция", "скидка", "промо", "бонус", "лояльность", "cashback",
    ],
    "tis": [
        "тис", "трёхкомпонентная", "ип", "упрощёнка", "910", "913",
    ],
}

# Common typos dictionary (Russian)
COMMON_TYPOS = {
    "сколько": ["скока", "сколко", "скоко", "скольк"],
    "стоимость": ["стоимсть", "стоимасть", "стоемость"],
    "цена": ["ценна", "цна", "цен", "ценa"],
    "бесплатно": ["беслатно", "безплатно", "бесплатна", "беспалтно"],
    "тариф": ["торифф", "тарив", "тарифф"],
    "интеграция": ["интеграця", "интегация", "интерграция"],
    "приложение": ["прилажение", "приложенее", "прилоение"],
    "оборудование": ["оборудованее", "абарудование", "оборудывание"],
    "поддержка": ["подержка", "паддержка", "поддержко"],
    "настройка": ["настройко", "натсройка", "настроика"],
    "функция": ["функцыя", "функия", "фунция"],
    "возможность": ["возможнось", "возможносьт", "вазможность"],
    "работает": ["работат", "роботает", "работаит"],
    "подключение": ["подлючение", "подключенее", "поключение"],
}

# Keyboard neighbors for typo generation (Russian layout)
KEYBOARD_NEIGHBORS_RU = {
    'й': 'цу', 'ц': 'йук', 'у': 'цке', 'к': 'у|ен', 'е': 'кнг',
    'н': 'егш', 'г': 'ншщ', 'ш': 'гщз', 'щ': 'шзх', 'з': 'щхъ',
    'х': 'зъ', 'ъ': 'х', 'ф': 'ыв', 'ы': 'фва', 'в': 'ыап',
    'а': 'впр', 'п': 'аро', 'р': 'пол', 'о': 'рлд', 'л': 'одж',
    'д': 'лжэ', 'ж': 'дэ', 'э': 'ж', 'я': 'чс', 'ч': 'яс',
    'с': 'ячм', 'м': 'сит', 'и': 'мть', 'т': 'иьб', 'ь': 'тб',
    'б': 'ью', 'ю': 'б',
}


@dataclass
class Config:
    """Main configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    # Paths
    input_path: Optional[Path] = None
    output_path: Optional[Path] = None

    # Runtime
    verbose: bool = False
    dry_run: bool = False
    parallel_workers: int = 1
