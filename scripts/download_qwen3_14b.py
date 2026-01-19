#!/usr/bin/env python3
"""
Скрипт для загрузки Qwen3-14B-AWQ модели из HuggingFace.
"""
import os
from pathlib import Path

def download_model():
    """Загрузить Qwen3-14B-AWQ модель."""
    print("=" * 60)
    print("Загрузка Qwen3-14B-AWQ модели")
    print("=" * 60)

    model_name = "Qwen/Qwen3-14B-AWQ"

    try:
        from huggingface_hub import snapshot_download

        print(f"\nМодель: {model_name}")
        print("Размер: ~8-9 GB")
        print("\nНачинаю загрузку...")

        # Загружаем модель в кеш HuggingFace
        model_path = snapshot_download(
            repo_id=model_name,
            cache_dir=os.path.expanduser("~/.cache/huggingface"),
            resume_download=True,
        )

        print(f"\n✓ Модель успешно загружена!")
        print(f"Путь: {model_path}")

        return model_path

    except ImportError:
        print("\n[!] huggingface_hub не установлен")
        print("Установите: pip install huggingface-hub")
        return None
    except Exception as e:
        print(f"\n[!] Ошибка при загрузке: {e}")
        return None

if __name__ == "__main__":
    path = download_model()
    if path:
        print("\n" + "=" * 60)
        print("Готово! Модель можно использовать.")
        print("=" * 60)
    else:
        print("\nЗагрузка не удалась.")
