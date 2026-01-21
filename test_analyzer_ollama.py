#!/usr/bin/env python3
"""Test codebase-analyzer with Ollama + Qwen3-14B."""

import asyncio
import httpx
from pathlib import Path

# Test file - TypeScript with 1294 lines
TEST_FILE = Path("/home/corta/.continue/types/core/index.d.ts")

# Ollama API (OpenAI-compatible)
OLLAMA_BASE = "http://localhost:11434/v1"
MODEL = "qwen3:14b"


async def test_ollama_connection():
    """Test basic Ollama connectivity."""
    print("=" * 60)
    print("1. Testing Ollama connection...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("http://localhost:11434/api/tags")
        models = resp.json()
        print(f"   Available models: {[m['name'] for m in models['models']]}")
        return True


async def test_typescript_parser():
    """Test TypeScript parser from codebase-analyzer."""
    print("=" * 60)
    print("2. Testing TypeScript parser...")

    from codebase_analyzer.indexer.parsers.typescript_parser import TypeScriptParser
    from codebase_analyzer.config import IndexerConfig

    parser = TypeScriptParser()

    # Parse the test file
    result = parser.parse_file(TEST_FILE)

    if not result:
        print("   Failed to parse file!")
        return None

    # Separate interfaces and classes
    interfaces = [c for c in result.classes if c.is_interface]
    classes = [c for c in result.classes if not c.is_interface]

    print(f"   File: {TEST_FILE.name}")
    print(f"   Lines: {result.line_count}")
    print(f"   Interfaces found: {len(interfaces)}")
    print(f"   Functions found: {len(result.functions)}")
    print(f"   Classes found: {len(classes)}")
    print(f"   Imports found: {len(result.imports)}")

    # Show some interfaces
    if interfaces:
        print(f"\n   Sample interfaces:")
        for iface in interfaces[:5]:
            print(f"     - {iface.name} (lines {iface.location.start_line}-{iface.location.end_line})")

    return result


async def test_llm_analysis(parsed_result):
    """Test LLM analysis via Ollama."""
    print("=" * 60)
    print("3. Testing LLM analysis with Qwen3-14B...")

    if not parsed_result:
        print("   No parsed result!")
        return

    # Pick first interface for analysis
    interfaces = [c for c in parsed_result.classes if c.is_interface]
    if not interfaces:
        print("   No interfaces to analyze, trying classes...")
        interfaces = parsed_result.classes

    if not interfaces:
        print("   No classes/interfaces found")
        return

    sample = interfaces[0]
    code_snippet = TEST_FILE.read_text().splitlines()[sample.location.start_line-1:sample.location.end_line]
    code_text = "\n".join(code_snippet)

    prompt = f"""Analyze this TypeScript interface and provide:
1. Purpose of the interface
2. Key properties and their roles
3. Potential use cases

```typescript
{code_text}
```

Respond in Russian. Be concise."""

    print(f"   Analyzing interface: {sample.name}")
    print(f"   Code lines: {sample.location.start_line}-{sample.location.end_line}")

    async with httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=120.0) as client:
        resp = await client.post(
            "/chat/completions",
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "You are a code analysis expert. /no_think"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1024,
                "temperature": 0.1,
            }
        )
        resp.raise_for_status()
        data = resp.json()

        response_text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        print(f"\n   Tokens: {usage.get('prompt_tokens', '?')} in, {usage.get('completion_tokens', '?')} out")
        print(f"\n   LLM Response:\n")
        print("-" * 40)
        print(response_text)
        print("-" * 40)


async def main():
    print("\n" + "=" * 60)
    print("CODEBASE-ANALYZER TEST with Ollama + Qwen3-14B")
    print("=" * 60)

    # 1. Test connection
    await test_ollama_connection()

    # 2. Test parser
    parsed = await test_typescript_parser()

    # 3. Test LLM
    await test_llm_analysis(parsed)

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
