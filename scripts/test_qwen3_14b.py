#!/usr/bin/env python3
"""
Тестовый скрипт для проверки Qwen3-14B через vLLM API.
"""
import requests
import json
import time

API_URL = "http://localhost:8000/v1"

def test_health():
    """Проверить здоровье сервера."""
    print("=" * 60)
    print("1. Проверка health endpoint...")
    print("=" * 60)
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✓ Сервер работает!")
        else:
            print(f"✗ Ошибка: статус {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Не удалось подключиться: {e}")
        return False
    return True

def test_models():
    """Получить список моделей."""
    print("\n" + "=" * 60)
    print("2. Получение списка моделей...")
    print("=" * 60)
    try:
        response = requests.get(f"{API_URL}/models", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = data.get("data", [])
            print(f"✓ Найдено моделей: {len(models)}")
            for model in models:
                print(f"  - {model['id']}")
        else:
            print(f"✗ Ошибка: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        return False
    return True

def test_completion():
    """Тест генерации текста."""
    print("\n" + "=" * 60)
    print("3. Тест генерации (chat completion)...")
    print("=" * 60)

    messages = [
        {
            "role": "system",
            "content": "Ты профессиональный менеджер по продажам CRM-системы. "
                      "Отвечай кратко и по делу на русском языке."
        },
        {
            "role": "user",
            "content": "Здравствуйте! Расскажите кратко, что умеет ваша CRM?"
        }
    ]

    payload = {
        "model": "Qwen/Qwen3-14B-AWQ",
        "messages": messages,
        "max_tokens": 200,
        "temperature": 0.7,
        "top_p": 0.9,
    }

    print("\nЗапрос:")
    print(f"  User: {messages[1]['content']}")
    print("\nОтвет модели:")

    try:
        start = time.time()
        response = requests.post(
            f"{API_URL}/chat/completions",
            json=payload,
            timeout=30
        )
        elapsed = time.time() - start

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            tokens = data["usage"]["completion_tokens"]

            print(f"  {content}\n")
            print(f"✓ Успешно!")
            print(f"  Токенов: {tokens}")
            print(f"  Время: {elapsed:.2f}с")
            print(f"  Скорость: {tokens/elapsed:.1f} tokens/sec")
        else:
            print(f"✗ Ошибка: {response.status_code}")
            print(f"  {response.text}")
            return False
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        return False

    return True

def test_classification():
    """Тест классификации интентов (для CRM бота)."""
    print("\n" + "=" * 60)
    print("4. Тест классификации интентов...")
    print("=" * 60)

    test_cases = [
        "Сколько стоит ваша CRM?",
        "Мне нужна демо-версия",
        "Нет, не интересно",
        "А можно попробовать бесплатно?",
    ]

    for msg in test_cases:
        messages = [
            {
                "role": "system",
                "content": "Классифицируй интент клиента: price_question, demo_request, "
                          "rejection, info_request. Отвечай одним словом."
            },
            {
                "role": "user",
                "content": msg
            }
        ]

        payload = {
            "model": "Qwen/Qwen3-14B-AWQ",
            "messages": messages,
            "max_tokens": 10,
            "temperature": 0.1,
        }

        try:
            response = requests.post(
                f"{API_URL}/chat/completions",
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                intent = data["choices"][0]["message"]["content"].strip()
                print(f"  '{msg}' → {intent}")
            else:
                print(f"  '{msg}' → ERROR")
        except Exception as e:
            print(f"  '{msg}' → ERROR: {e}")

    print("\n✓ Классификация завершена")
    return True

def main():
    """Запуск всех тестов."""
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ QWEN3-14B-AWQ")
    print("=" * 60 + "\n")

    if not test_health():
        print("\n[!] vLLM сервер не запущен!")
        print("Запустите: ./scripts/start_vllm_qwen3_14b.sh")
        return

    if not test_models():
        print("\n[!] Не удалось получить список моделей")
        return

    if not test_completion():
        print("\n[!] Ошибка генерации")
        return

    if not test_classification():
        print("\n[!] Ошибка классификации")
        return

    print("\n" + "=" * 60)
    print("✓ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("=" * 60)
    print("\nМодель Qwen3-14B-AWQ готова к использованию.")
    print("Теперь можно запустить CRM бота с новой моделью.\n")

if __name__ == "__main__":
    main()
