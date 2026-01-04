"""
LLM клиент для Ollama
"""

import requests
from settings import settings


class OllamaLLM:
    def __init__(
        self,
        model: str = None,
        base_url: str = None,
        timeout: int = None
    ):
        # Берём из settings если не указано явно
        self.model = model or settings.llm.model
        self.base_url = base_url or settings.llm.base_url
        self.timeout = timeout or settings.llm.timeout
        self.stream = settings.llm.stream
        self.think = settings.llm.think

    def generate(self, prompt: str) -> str:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": self.stream,
                "think": self.think,
            },
            timeout=self.timeout
        )
        return response.json()["response"]


if __name__ == "__main__":
    llm = OllamaLLM()
    print(f"Model: {llm.model}")
    print(f"URL: {llm.base_url}")
    print(f"Timeout: {llm.timeout}")
    print(llm.generate("Привет! Ты работаешь?"))
