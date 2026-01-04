"""
Test LLM with Ollama
Tests response generation and streaming
"""
import time
import ollama
from rich.console import Console
from rich.live import Live
from rich.text import Text

console = Console()


def test_llm_basic(model: str = "qwen3:8b"):
    """Test basic LLM response"""
    print("=" * 50)
    print(f"🤖 LLM Test (Ollama - {model})")
    print("=" * 50)

    prompt = "Привет! Расскажи кратко, что такое искусственный интеллект?"

    print(f"\n📝 Prompt: {prompt}")
    print("\n🔄 Generating response...")

    start_time = time.time()

    response = ollama.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Ты полезный ассистент. Отвечай кратко и по делу на русском языке."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    elapsed = time.time() - start_time
    text = response["message"]["content"]

    print("\n" + "=" * 50)
    print("📊 Results:")
    print("=" * 50)
    print(f"💬 Response: {text}")
    print(f"\n⏱️  Total time: {elapsed:.2f}s")

    return text, elapsed


def test_llm_streaming(model: str = "qwen3:8b"):
    """Test streaming LLM response"""
    print("\n" + "=" * 50)
    print(f"🌊 LLM Streaming Test (Ollama - {model})")
    print("=" * 50)

    prompt = "Перечисли 5 преимуществ голосовых ассистентов."

    print(f"\n📝 Prompt: {prompt}")
    print("\n🔄 Streaming response:\n")

    start_time = time.time()
    first_token_time = None
    full_response = ""

    stream = ollama.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Ты полезный ассистент. Отвечай кратко и по делу на русском языке."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        stream=True
    )

    for chunk in stream:
        if first_token_time is None:
            first_token_time = time.time() - start_time

        content = chunk["message"]["content"]
        full_response += content
        print(content, end="", flush=True)

    elapsed = time.time() - start_time

    print("\n\n" + "=" * 50)
    print("📊 Streaming Results:")
    print("=" * 50)
    print(f"⏱️  Time to first token: {first_token_time:.2f}s")
    print(f"⏱️  Total time: {elapsed:.2f}s")
    print(f"📏 Response length: {len(full_response)} chars")

    return full_response, first_token_time, elapsed


def test_llm():
    """Run all LLM tests"""
    # Check available models
    print("📋 Available models:")
    models = ollama.list()
    for m in models.models:
        print(f"   - {m.model}")

    # Use available model
    model = "qwen3:8b"

    # Run tests
    test_llm_basic(model)
    test_llm_streaming(model)


if __name__ == "__main__":
    test_llm()
