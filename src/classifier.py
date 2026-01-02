"""
Классификатор интентов + извлечение данных
"""

import re
from typing import Dict, Tuple
from config import INTENT_EXAMPLES


class IntentClassifier:
    def __init__(self):
        self.examples = INTENT_EXAMPLES
    
    def classify(self, message: str) -> Tuple[str, float]:
        """Классификация по ключевым словам"""
        message_lower = message.lower()
        
        best_intent = "unclear"
        best_score = 0.0
        
        for intent, examples in self.examples.items():
            score = 0
            for example in examples:
                if example in message_lower:
                    score += 1
            
            if score > best_score:
                best_score = score
                best_intent = intent
        
        confidence = min(best_score / 2, 1.0) if best_score > 0 else 0.3
        return best_intent, confidence


class DataExtractor:
    def extract(self, message: str) -> Dict:
        """Извлекаем данные из сообщения"""
        extracted = {}
        message_lower = message.lower()
        
        # Размер компании
        patterns = [
            r'(\d+)\s*(?:человек|чел|менеджер|сотрудник)',
            r'нас\s*(\d+)',
            r'команд[аы]?\s*(?:из|в)?\s*(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                extracted["company_size"] = int(match.group(1))
                break
        
        # Боль клиента
        pain_keywords = {
            "теряем": "теряют клиентов",
            "забыва": "забывают перезванивать",
            "нет контроля": "нет контроля над менеджерами",
            "excel": "ведут в Excel",
        }
        for keyword, pain in pain_keywords.items():
            if keyword in message_lower:
                extracted["pain_point"] = pain
                break
        
        # Контакт
        email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', message)
        if email:
            extracted["contact_info"] = email.group(0)
        
        phone = re.search(r'[\+]?[\d\s\-\(\)]{10,}', message)
        if phone and "contact_info" not in extracted:
            extracted["contact_info"] = phone.group(0).strip()
        
        return extracted


class HybridClassifier:
    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.data_extractor = DataExtractor()
    
    def classify(self, message: str) -> Dict:
        """Полная классификация сообщения"""
        extracted = self.data_extractor.extract(message)
        
        # Если есть данные — это info_provided
        if extracted.get("company_size") or extracted.get("pain_point") or extracted.get("contact_info"):
            return {
                "intent": "info_provided",
                "confidence": 0.9,
                "extracted_data": extracted
            }
        
        intent, confidence = self.intent_classifier.classify(message)
        
        return {
            "intent": intent,
            "confidence": confidence,
            "extracted_data": extracted
        }


if __name__ == "__main__":
    classifier = HybridClassifier()
    
    print("=== Тест классификатора ===\n")
    
    tests = [
        "Привет!",
        "Сколько стоит?",
        "Дорого, нет бюджета",
        "У нас 15 человек в отделе",
        "Постоянно теряем клиентов",
        "Да, интересно",
        "Нет, не нужно",
        "Мой email: test@mail.ru",
    ]
    
    for msg in tests:
        result = classifier.classify(msg)
        print(f"'{msg}'")
        print(f"  Intent: {result['intent']} ({result['confidence']:.1f})")
        if result['extracted_data']:
            print(f"  Data: {result['extracted_data']}")
        print()